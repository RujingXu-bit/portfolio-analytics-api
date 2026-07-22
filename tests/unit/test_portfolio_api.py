from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import fields
from datetime import date
from decimal import Decimal
from math import sqrt
from uuid import UUID

import httpx
import pytest

from portfolio_analytics_api.api import create_app
from portfolio_analytics_api.application import (
    InsightGenerator,
    MarketDataInvalidResponseError,
    MarketDataProvider,
    MarketDataRateLimitError,
    MarketDataResult,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
    UnitOfWork,
)
from portfolio_analytics_api.domain import (
    AnalyticsMethodology,
    GeneratedInsight,
    PriceBar,
)
from portfolio_analytics_api.infrastructure import (
    Argon2PasswordHasher,
    FakeInsightGenerator,
    FakeMarketDataProvider,
    InMemoryStore,
    InMemoryUnitOfWork,
    JwtAccessTokenService,
)


@asynccontextmanager
async def api_client(
    price_bars_by_symbol: dict[str, tuple[PriceBar, ...]],
    market_data_provider: MarketDataProvider | None = None,
    insight_generator: InsightGenerator | None = None,
    store: InMemoryStore | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    actual_store = store or InMemoryStore()

    def unit_of_work_factory() -> UnitOfWork:
        return InMemoryUnitOfWork(actual_store)

    app = create_app(
        unit_of_work_factory=unit_of_work_factory,
        market_data_provider=(
            market_data_provider
            if market_data_provider is not None
            else FakeMarketDataProvider(price_bars_by_symbol)
        ),
        methodology=AnalyticsMethodology(
            annual_risk_free_rate=Decimal("0"),
            risk_free_rate_as_of=date(2026, 1, 1),
            risk_free_rate_assumption="Fixed offline test rate.",
        ),
        password_hasher=Argon2PasswordHasher(),
        access_token_service=JwtAccessTokenService(
            secret_key="unit-test-secret-key-with-32-characters",
            expire_minutes=30,
        ),
        insight_generator=insight_generator,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        registration = await client.post(
            "/auth/register",
            json={
                "email": "owner@example.com",
                "password": "portfolio owner password",
            },
        )
        assert registration.status_code == 201
        login = await client.post(
            "/auth/login",
            json={
                "email": "owner@example.com",
                "password": "portfolio owner password",
            },
        )
        assert login.status_code == 200
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        yield client


def buy_transaction(
    symbol: str = "DEMO", external_id: str = "buy-001", quantity: str = "2"
) -> dict[str, str]:
    return {
        "external_id": external_id,
        "transaction_type": "BUY",
        "occurred_at": "2026-01-02T09:00:00Z",
        "symbol": symbol,
        "quantity": quantity,
        "unit_price": "100",
        "fees": "0.25",
    }


async def create_portfolio(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/portfolios",
        json={"name": " Offline demo ", "base_currency": "usd"},
    )

    assert response.status_code == 201
    body = response.json()
    UUID(body["id"])
    assert body == {
        "id": body["id"],
        "name": "Offline demo",
        "base_currency": "USD",
    }
    return str(body["id"])


@pytest.mark.anyio
async def test_portfolio_list_is_owner_scoped_newest_first_and_paginated() -> None:
    async with api_client({}) as client:
        created = []
        for name in ("First", "Second", "Third"):
            response = await client.post("/portfolios", json={"name": name})
            assert response.status_code == 201
            created.append(response.json())

        page = await client.get("/portfolios", params={"limit": 2, "offset": 1})

        second_login = await client.post(
            "/auth/register",
            json={
                "email": "other@example.com",
                "password": "another owner password",
            },
        )
        assert second_login.status_code == 201
        login = await client.post(
            "/auth/login",
            json={
                "email": "other@example.com",
                "password": "another owner password",
            },
        )
        other_page = await client.get(
            "/portfolios",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )

    assert page.status_code == 200
    assert page.json() == {
        "items": [created[1], created[0]],
        "total": 3,
        "limit": 2,
        "offset": 1,
    }
    assert other_page.status_code == 200
    assert other_page.json() == {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        "/portfolios?limit=0",
        "/portfolios?limit=101",
        "/portfolios?offset=-1",
    ],
)
async def test_portfolio_list_rejects_invalid_pagination(path: str) -> None:
    async with api_client({}) as client:
        response = await client.get(path)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.anyio
async def test_openapi_exposes_paginated_portfolio_and_snapshot_queries() -> None:
    async with api_client({}) as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "get" in paths["/portfolios"]
    assert "get" in paths["/portfolios/{portfolio_id}/insights"]
    schemas = response.json()["components"]["schemas"]
    assert "PortfolioPageResponse" in schemas
    assert "AnalysisSnapshotPageResponse" in schemas


@pytest.mark.anyio
async def test_persistent_api_returns_portfolio_transactions_and_metrics() -> None:
    prices = (
        PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),
        PriceBar("DEMO", date(2026, 1, 5), Decimal("110")),
        PriceBar("DEMO", date(2026, 1, 6), Decimal("99")),
    )
    async with api_client({"DEMO": prices}) as client:
        portfolio_id = await create_portfolio(client)

        portfolio_response = await client.get(f"/portfolios/{portfolio_id}")
        transaction_response = await client.post(
            f"/portfolios/{portfolio_id}/transactions",
            json=buy_transaction(symbol=" demo "),
        )
        list_response = await client.get(f"/portfolios/{portfolio_id}/transactions")
        analytics_response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
        )

    assert portfolio_response.status_code == 200
    assert portfolio_response.json()["base_currency"] == "USD"
    assert transaction_response.status_code == 201
    transaction = transaction_response.json()
    UUID(transaction["id"])
    assert transaction["portfolio_id"] == portfolio_id
    assert transaction["symbol"] == "DEMO"
    assert list_response.status_code == 200
    assert list_response.json() == [transaction]

    assert analytics_response.status_code == 200
    body = analytics_response.json()
    assert body["as_of"] == "2026-01-06"
    assert body["simple_return"] == pytest.approx(-0.01)
    assert body["annualized_volatility"] == pytest.approx(0.2 / sqrt(2) * sqrt(252))
    assert body["max_drawdown"] == pytest.approx(-0.1)
    assert body["sharpe_ratio"] == pytest.approx(0.0)
    assert Decimal(body["portfolio_value"]) == Decimal("198")
    assert Decimal(body["cash_balance"]) == 0
    assert body["asset_weights"][0]["symbol"] == "DEMO"
    assert Decimal(body["asset_weights"][0]["market_value"]) == Decimal("198")
    assert Decimal(body["asset_weights"][0]["weight"]) == 1
    assert body["methodology"]["price_basis"] == "adjusted_close"
    assert body["methodology"]["valuation_method"] == ("end_of_day_cash_flow_adjusted")
    assert body["stale"] is False


@pytest.mark.anyio
async def test_identical_transaction_retry_returns_existing_with_200() -> None:
    async with api_client({}) as client:
        portfolio_id = await create_portfolio(client)
        first = await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_transaction()
        )
        retry = await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_transaction()
        )
        listed = await client.get(f"/portfolios/{portfolio_id}/transactions")

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json()["id"] == first.json()["id"]
    assert listed.json() == [first.json()]


@pytest.mark.anyio
async def test_idempotency_payload_conflict_has_stable_409() -> None:
    async with api_client({}) as client:
        portfolio_id = await create_portfolio(client)
        await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_transaction()
        )
        response = await client.post(
            f"/portfolios/{portfolio_id}/transactions",
            json=buy_transaction(quantity="3"),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "transaction_idempotency_conflict"


@pytest.mark.anyio
async def test_oversell_has_stable_domain_error() -> None:
    async with api_client({}) as client:
        portfolio_id = await create_portfolio(client)
        response = await client.post(
            f"/portfolios/{portfolio_id}/transactions",
            json={
                **buy_transaction(),
                "external_id": "sell-001",
                "transaction_type": "SELL",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_transaction"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   "},
        {
            "name": "Valid",
            "base_currency": "EURO",
        },
    ],
)
async def test_portfolio_validation_uses_stable_error_shape(
    payload: dict[str, str],
) -> None:
    async with api_client({}) as client:
        response = await client.post("/portfolios", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "request validation failed",
        }
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {
            **buy_transaction(),
            "occurred_at": "2026-01-02T09:00:00",
        },
        {
            **buy_transaction(),
            "cash_amount": "100",
        },
        {
            "external_id": "deposit-001",
            "transaction_type": "DEPOSIT",
            "occurred_at": "2026-01-02T09:00:00Z",
        },
        {
            **buy_transaction(),
            "unit_price": "1.123456789",
        },
    ],
)
async def test_transaction_validation_uses_stable_error_shape(
    payload: dict[str, str],
) -> None:
    async with api_client({}) as client:
        portfolio_id = await create_portfolio(client)
        response = await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=payload
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.anyio
async def test_missing_portfolio_has_stable_not_found_errors() -> None:
    portfolio_id = "00000000-0000-0000-0000-000000000001"
    async with api_client({}) as client:
        responses = (
            await client.get(f"/portfolios/{portfolio_id}"),
            await client.get(f"/portfolios/{portfolio_id}/transactions"),
            await client.post(
                f"/portfolios/{portfolio_id}/transactions", json=buy_transaction()
            ),
            await client.get(
                f"/portfolios/{portfolio_id}/analytics",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            ),
            await client.get(f"/portfolios/{portfolio_id}/insights"),
        )

    assert all(response.status_code == 404 for response in responses)
    assert all(
        response.json()["error"]["code"] == "portfolio_not_found"
        for response in responses
    )


@pytest.mark.anyio
async def test_portfolio_routes_require_bearer_authentication() -> None:
    async with api_client({}) as client:
        del client.headers["Authorization"]
        responses = (
            await client.post("/portfolios", json={"name": "Private"}),
            await client.get("/portfolios"),
        )

    assert all(response.status_code == 401 for response in responses)
    assert all(
        response.headers["www-authenticate"] == "Bearer" for response in responses
    )
    assert all(
        response.json()["error"]["code"] == "authentication_failed"
        for response in responses
    )


@pytest.mark.anyio
async def test_direct_id_guess_cannot_access_another_users_resources() -> None:
    async with api_client({}) as client:
        portfolio_id = await create_portfolio(client)
        second_registration = await client.post(
            "/auth/register",
            json={
                "email": "other@example.com",
                "password": "another owner password",
            },
        )
        assert second_registration.status_code == 201
        second_login = await client.post(
            "/auth/login",
            json={
                "email": "other@example.com",
                "password": "another owner password",
            },
        )
        other_headers = {
            "Authorization": f"Bearer {second_login.json()['access_token']}"
        }
        responses = (
            await client.get(f"/portfolios/{portfolio_id}", headers=other_headers),
            await client.get(
                f"/portfolios/{portfolio_id}/transactions", headers=other_headers
            ),
            await client.post(
                f"/portfolios/{portfolio_id}/transactions",
                json=buy_transaction(),
                headers=other_headers,
            ),
            await client.get(
                f"/portfolios/{portfolio_id}/analytics",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
                headers=other_headers,
            ),
            await client.post(
                f"/portfolios/{portfolio_id}/insights",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
                headers=other_headers,
            ),
            await client.get(
                f"/portfolios/{portfolio_id}/insights", headers=other_headers
            ),
        )

    assert all(response.status_code == 404 for response in responses)
    assert all(
        response.json()["error"]["code"] == "portfolio_not_found"
        for response in responses
    )


@pytest.mark.anyio
async def test_multi_symbol_analytics_returns_latest_asset_weights() -> None:
    prices: dict[str, tuple[PriceBar, ...]] = {
        "DEMO": (
            PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),
            PriceBar("DEMO", date(2026, 1, 3), Decimal("110")),
        ),
        "OTHER": (
            PriceBar("OTHER", date(2026, 1, 2), Decimal("100")),
            PriceBar("OTHER", date(2026, 1, 3), Decimal("90")),
        ),
    }
    async with api_client(prices) as client:
        portfolio_id = await create_portfolio(client)
        await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_transaction()
        )
        await client.post(
            f"/portfolios/{portfolio_id}/transactions",
            json=buy_transaction("OTHER", "buy-002"),
        )
        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

    assert response.status_code == 200
    assert [weight["symbol"] for weight in response.json()["asset_weights"]] == [
        "DEMO",
        "OTHER",
    ]


@pytest.mark.anyio
async def test_unknown_symbol_has_stable_market_data_error() -> None:
    async with api_client({}) as client:
        portfolio_id = await create_portfolio(client)
        await client.post(
            f"/portfolios/{portfolio_id}/transactions",
            json=buy_transaction(symbol="UNKNOWN"),
        )
        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "market_data_not_found"


@pytest.mark.anyio
async def test_invalid_date_range_has_stable_analytics_error() -> None:
    async with api_client({}) as client:
        portfolio_id = await create_portfolio(client)
        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-02-01", "end_date": "2026-01-01"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "analytics_unavailable"


@pytest.mark.anyio
async def test_invalid_price_series_has_stable_error() -> None:
    prices = (
        PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),
        PriceBar("DEMO", date(2026, 1, 2), Decimal("101")),
    )
    async with api_client({"DEMO": prices}) as client:
        portfolio_id = await create_portfolio(client)
        await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_transaction()
        )
        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_price_series"


class ResultMarketDataProvider:
    def __init__(self, result: MarketDataResult | Exception) -> None:
        self._result = result

    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> MarketDataResult:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


@pytest.mark.anyio
async def test_stale_market_data_is_explicit_in_analytics_response() -> None:
    result = MarketDataResult(
        (
            PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),
            PriceBar("DEMO", date(2026, 1, 5), Decimal("101")),
        ),
        stale=True,
    )
    async with api_client({}, ResultMarketDataProvider(result)) as client:
        portfolio_id = await create_portfolio(client)
        await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_transaction()
        )
        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

    assert response.status_code == 200
    assert response.json()["stale"] is True


@pytest.mark.anyio
async def test_rule_based_insight_is_stable_and_offline() -> None:
    prices = (
        PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),
        PriceBar("DEMO", date(2026, 1, 5), Decimal("110")),
        PriceBar("DEMO", date(2026, 1, 6), Decimal("99")),
    )
    async with api_client({"DEMO": prices}) as client:
        portfolio_id = await create_portfolio(client)
        await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_transaction()
        )
        first = await client.post(
            f"/portfolios/{portfolio_id}/insights",
            params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
        )
        second = await client.post(
            f"/portfolios/{portfolio_id}/insights",
            params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
        )

    assert first.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    assert body["generator"] == "deterministic_rules"
    assert body["model_name"] is None
    assert body["prompt_version"] == "risk-rules-v1"
    assert body["disclaimer"] == (
        "For informational purposes only; not investment advice."
    )


@pytest.mark.anyio
async def test_insight_history_is_newest_first_paginated_and_structured() -> None:
    prices = (
        PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),
        PriceBar("DEMO", date(2026, 1, 5), Decimal("110")),
        PriceBar("DEMO", date(2026, 1, 6), Decimal("99")),
    )
    async with api_client({"DEMO": prices}) as client:
        portfolio_id = await create_portfolio(client)
        transaction = await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_transaction()
        )
        assert transaction.status_code == 201
        for _ in range(2):
            insight = await client.post(
                f"/portfolios/{portfolio_id}/insights",
                params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
            )
            assert insight.status_code == 200

        full_page = await client.get(f"/portfolios/{portfolio_id}/insights")
        second_page = await client.get(
            f"/portfolios/{portfolio_id}/insights",
            params={"limit": 1, "offset": 1},
        )

    assert full_page.status_code == 200
    body = full_page.json()
    assert body["total"] == 2
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    assert body["items"][0]["generated_at"] >= body["items"][1]["generated_at"]
    snapshot = body["items"][0]
    UUID(snapshot["id"])
    assert snapshot["as_of"] == "2026-01-06"
    assert snapshot["metrics"]["as_of"] == "2026-01-06"
    assert snapshot["metrics"]["asset_weights"] == [{"symbol": "DEMO", "weight": "1"}]
    assert snapshot["metrics"]["stale"] is False
    assert snapshot["methodology"]["price_basis"] == "adjusted_close"
    assert snapshot["summary"]
    assert snapshot["generator"] == "deterministic_rules"
    assert snapshot["model_name"] is None
    assert snapshot["prompt_version"] == "risk-rules-v1"
    assert second_page.status_code == 200
    assert second_page.json() == {
        "items": [body["items"][1]],
        "total": 2,
        "limit": 1,
        "offset": 1,
    }


@pytest.mark.anyio
async def test_fake_generator_enriches_rules_and_records_snapshot() -> None:
    prices = (
        PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),
        PriceBar("DEMO", date(2026, 1, 5), Decimal("110")),
        PriceBar("DEMO", date(2026, 1, 6), Decimal("99")),
    )
    generated = GeneratedInsight(
        summary=(
            "The supplied historical metrics show material variability and "
            "concentration."
        ),
        additional_limitations=("The observation window is short.",),
    )
    generator = FakeInsightGenerator(generated)
    store = InMemoryStore()
    async with api_client(
        {"DEMO": prices}, insight_generator=generator, store=store
    ) as client:
        portfolio_id = await create_portfolio(client)
        await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_transaction()
        )
        response = await client.post(
            f"/portfolios/{portfolio_id}/insights",
            params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["generator"] == "fake"
    assert body["model_name"] == "fake-model"
    assert body["prompt_version"] == "fake-prompt-v1"
    assert body["risk_level"] == "high"
    assert body["summary"] == generated.summary
    assert "The observation window is short." in body["limitations"]
    assert len(generator.inputs) == 1
    assert {field.name for field in fields(generator.inputs[0])} == {
        "as_of",
        "simple_return",
        "annualized_volatility",
        "max_drawdown",
        "sharpe_ratio",
        "asset_weights",
        "methodology",
        "stale",
    }
    snapshot = store.analysis_snapshots[0]
    assert snapshot.generator == "fake"
    assert snapshot.model_name == "fake-model"
    assert snapshot.prompt_version == "fake-prompt-v1"
    assert snapshot.metrics["as_of"] == "2026-01-06"
    assert snapshot.methodology["price_basis"] == "adjusted_close"


@pytest.mark.anyio
async def test_generator_failure_returns_rules_and_keeps_analytics_available() -> None:
    prices = (
        PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),
        PriceBar("DEMO", date(2026, 1, 5), Decimal("110")),
        PriceBar("DEMO", date(2026, 1, 6), Decimal("99")),
    )
    generator = FakeInsightGenerator(TimeoutError("simulated timeout"))
    store = InMemoryStore()
    async with api_client(
        {"DEMO": prices}, insight_generator=generator, store=store
    ) as client:
        portfolio_id = await create_portfolio(client)
        await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_transaction()
        )
        insight = await client.post(
            f"/portfolios/{portfolio_id}/insights",
            params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
        )
        analytics = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
        )

    assert insight.status_code == analytics.status_code == 200
    assert insight.json()["generator"] == "deterministic_rules"
    assert insight.json()["model_name"] is None
    assert store.analysis_snapshots[0].generator == "deterministic_rules"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (
            MarketDataInvalidResponseError("bad payload"),
            502,
            "market_data_invalid_response",
        ),
        (MarketDataRateLimitError(), 503, "market_data_rate_limited"),
        (MarketDataUnavailableError(), 503, "market_data_unavailable"),
        (MarketDataTimeoutError(), 504, "market_data_timeout"),
    ],
)
async def test_market_data_failures_have_stable_http_mapping(
    error: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    async with api_client({}, ResultMarketDataProvider(error)) as client:
        portfolio_id = await create_portfolio(client)
        await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_transaction()
        )
        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
