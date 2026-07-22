from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from portfolio_analytics_api.api import create_app
from portfolio_analytics_api.application import InsightGenerator, UnitOfWork
from portfolio_analytics_api.core import Settings
from portfolio_analytics_api.domain import (
    AnalyticsMethodology,
    GeneratedInsight,
    PriceBar,
)
from portfolio_analytics_api.infrastructure import (
    Argon2PasswordHasher,
    FakeInsightGenerator,
    FakeMarketDataProvider,
    JwtAccessTokenService,
)
from portfolio_analytics_api.infrastructure.database import (
    SqlAlchemyUnitOfWork,
    create_database_engine,
    create_session_factory,
)
from portfolio_analytics_api.infrastructure.database.models import (
    AnalysisSnapshotRecord,
    PortfolioRecord,
)

PRICES = (
    PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),
    PriceBar("DEMO", date(2026, 1, 5), Decimal("110")),
    PriceBar("DEMO", date(2026, 1, 6), Decimal("99")),
)
OTHER_PRICES = (
    PriceBar("OTHER", date(2026, 1, 2), Decimal("50")),
    PriceBar("OTHER", date(2026, 1, 5), Decimal("55")),
    PriceBar("OTHER", date(2026, 1, 6), Decimal("60")),
)
METHODOLOGY = AnalyticsMethodology(
    annual_risk_free_rate=Decimal("0"),
    risk_free_rate_as_of=date(2026, 1, 1),
    risk_free_rate_assumption="Fixed integration-test rate.",
)


def build_test_app(
    engine: AsyncEngine,
    insight_generator: InsightGenerator | None = None,
) -> FastAPI:
    session_factory = create_session_factory(engine)

    def unit_of_work_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return create_app(
        unit_of_work_factory=unit_of_work_factory,
        market_data_provider=FakeMarketDataProvider(
            {"DEMO": PRICES, "OTHER": OTHER_PRICES}
        ),
        methodology=METHODOLOGY,
        password_hasher=Argon2PasswordHasher(),
        access_token_service=JwtAccessTokenService(
            secret_key="integration-test-secret-key-32-characters",
            expire_minutes=30,
        ),
        insight_generator=insight_generator,
        shutdown_callback=engine.dispose,
    )


def buy_payload(
    *,
    external_id: str = "buy-001",
    quantity: str = "2",
    symbol: str = "DEMO",
    unit_price: str = "100.12345678",
) -> dict[str, str]:
    return {
        "external_id": external_id,
        "transaction_type": "BUY",
        "occurred_at": "2026-01-02T09:00:00Z",
        "symbol": symbol,
        "quantity": quantity,
        "unit_price": unit_price,
        "fees": "0.00000001",
    }


def csv_import_payload() -> bytes:
    return (
        b"external_id,transaction_type,occurred_at,symbol,quantity,unit_price,"
        b"cash_amount,fees\n"
        b"db-deposit,DEPOSIT,2026-01-01T09:00:00Z,,,,1000,0\n"
        b"db-buy,BUY,2026-01-02T09:00:00Z,DEMO,2,100,,0.25\n"
        b"db-sell,SELL,2026-01-03T09:00:00Z,DEMO,1,110,,0.10\n"
        b"db-invalid,SELL,2026-01-04T09:00:00Z,DEMO,5,110,,0\n"
    )


async def authenticate(
    client: httpx.AsyncClient,
    email: str = "owner@example.com",
    password: str = "persistent owner password",
) -> str:
    registration = await client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert registration.status_code == 201
    login = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200
    token = str(login.json()["access_token"])
    client.headers["Authorization"] = f"Bearer {token}"
    return token


@pytest.mark.anyio
async def test_portfolio_list_is_persisted_owner_scoped_and_paginated(
    database_engine: AsyncEngine,
) -> None:
    app = build_test_app(database_engine)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await authenticate(client)
        created = []
        for name in ("First", "Second", "Third"):
            response = await client.post("/portfolios", json={"name": name})
            assert response.status_code == 201
            created.append(response.json())

        session_factory = create_session_factory(database_engine)
        async with session_factory() as session:
            for index, portfolio in enumerate(created):
                await session.execute(
                    update(PortfolioRecord)
                    .where(PortfolioRecord.id == UUID(portfolio["id"]))
                    .values(created_at=datetime(2026, 1, index + 1, tzinfo=UTC))
                )
            await session.commit()

        page = await client.get("/portfolios", params={"limit": 2, "offset": 1})

        await authenticate(
            client,
            email="other@example.com",
            password="persistent other password",
        )
        other_page = await client.get("/portfolios")

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
async def test_all_endpoints_persist_across_app_and_engine_recreation(
    database_engine: AsyncEngine,
) -> None:
    first_app = build_test_app(database_engine)
    first_transport = httpx.ASGITransport(app=first_app)
    async with httpx.AsyncClient(
        transport=first_transport, base_url="http://test"
    ) as client:
        access_token = await authenticate(client)
        portfolio_response = await client.post(
            "/portfolios", json={"name": "Persistent", "base_currency": "USD"}
        )
        portfolio_id = portfolio_response.json()["id"]
        transaction_response = await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_payload()
        )
        analytics_response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
        )

    assert portfolio_response.status_code == 201
    assert transaction_response.status_code == 201
    assert analytics_response.status_code == 200
    await database_engine.dispose()

    second_engine = create_database_engine(Settings().test_database_url)
    try:
        second_app = build_test_app(second_engine)
        second_transport = httpx.ASGITransport(app=second_app)
        async with httpx.AsyncClient(
            transport=second_transport, base_url="http://test"
        ) as client:
            client.headers["Authorization"] = f"Bearer {access_token}"
            portfolio_after_restart = await client.get(f"/portfolios/{portfolio_id}")
            transactions_after_restart = await client.get(
                f"/portfolios/{portfolio_id}/transactions"
            )
            analytics_after_restart = await client.get(
                f"/portfolios/{portfolio_id}/analytics",
                params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
            )
    finally:
        await second_engine.dispose()

    assert portfolio_after_restart.status_code == 200
    assert portfolio_after_restart.json() == portfolio_response.json()
    assert transactions_after_restart.status_code == 200
    assert transactions_after_restart.json() == [transaction_response.json()]
    assert analytics_after_restart.status_code == 200
    assert analytics_after_restart.json() == analytics_response.json()


@pytest.mark.anyio
async def test_csv_import_persists_valid_rows_and_replays_database_ids(
    database_engine: AsyncEngine,
) -> None:
    app = build_test_app(database_engine)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await authenticate(client)
        portfolio = await client.post("/portfolios", json={"name": "CSV import"})
        portfolio_id = portfolio.json()["id"]
        path = f"/portfolios/{portfolio_id}/transactions/import"

        preview = await client.post(
            f"{path}/preview",
            content=csv_import_payload(),
            headers={"Content-Type": "text/csv"},
        )
        first = await client.post(
            path,
            content=csv_import_payload(),
            headers={"Content-Type": "text/csv"},
        )
        retry = await client.post(
            path,
            content=csv_import_payload(),
            headers={"Content-Type": "text/csv"},
        )
        ledger = await client.get(f"/portfolios/{portfolio_id}/transactions")

    assert preview.json()["summary"] == {
        "total_rows": 4,
        "ready_rows": 3,
        "replay_rows": 0,
        "invalid_rows": 1,
    }
    assert first.json()["summary"] == {
        "total_rows": 4,
        "created_rows": 3,
        "replayed_rows": 0,
        "failed_rows": 1,
    }
    assert retry.json()["summary"] == {
        "total_rows": 4,
        "created_rows": 0,
        "replayed_rows": 3,
        "failed_rows": 1,
    }
    first_ids = [
        row["transaction"]["id"]
        for row in first.json()["rows"]
        if row["transaction"] is not None
    ]
    retry_ids = [
        row["transaction"]["id"]
        for row in retry.json()["rows"]
        if row["transaction"] is not None
    ]
    assert retry_ids == first_ids
    assert len(ledger.json()) == 3


@pytest.mark.anyio
async def test_persistent_api_values_multiple_assets(
    database_engine: AsyncEngine,
) -> None:
    app = build_test_app(database_engine)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await authenticate(client)
        portfolio = await client.post("/portfolios", json={"name": "Multi asset"})
        portfolio_id = portfolio.json()["id"]
        await client.post(
            f"/portfolios/{portfolio_id}/transactions",
            json=buy_payload(),
        )
        await client.post(
            f"/portfolios/{portfolio_id}/transactions",
            json=buy_payload(
                external_id="buy-002",
                quantity="1",
                symbol="OTHER",
                unit_price="50",
            ),
        )
        analytics = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
        )

    assert analytics.status_code == 200
    body = analytics.json()
    assert Decimal(body["portfolio_value"]) == Decimal("258")
    assert Decimal(body["cash_balance"]) == 0
    assert [weight["symbol"] for weight in body["asset_weights"]] == [
        "DEMO",
        "OTHER",
    ]


@pytest.mark.anyio
async def test_persistent_api_maps_idempotency_and_domain_errors(
    database_engine: AsyncEngine,
) -> None:
    app = build_test_app(database_engine)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await authenticate(client)
        portfolio = await client.post("/portfolios", json={"name": "Errors"})
        portfolio_id = portfolio.json()["id"]
        oversell = await client.post(
            f"/portfolios/{portfolio_id}/transactions",
            json={**buy_payload(), "transaction_type": "SELL"},
        )
        first = await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_payload()
        )
        retry = await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_payload()
        )
        conflict = await client.post(
            f"/portfolios/{portfolio_id}/transactions",
            json=buy_payload(quantity="3"),
        )

    assert oversell.status_code == 422
    assert oversell.json()["error"]["code"] == "invalid_transaction"
    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json()["id"] == first.json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "transaction_idempotency_conflict"


@pytest.mark.anyio
async def test_persistent_api_denies_cross_user_direct_id_access(
    database_engine: AsyncEngine,
) -> None:
    app = build_test_app(database_engine)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await authenticate(client)
        portfolio = await client.post("/portfolios", json={"name": "Private"})
        portfolio_id = portfolio.json()["id"]
        await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_payload()
        )

        await authenticate(
            client,
            email="other@example.com",
            password="persistent other password",
        )
        responses = (
            await client.get(f"/portfolios/{portfolio_id}"),
            await client.get(f"/portfolios/{portfolio_id}/transactions"),
            await client.post(
                f"/portfolios/{portfolio_id}/transactions",
                json=buy_payload(external_id="other-buy"),
            ),
            await client.post(
                f"/portfolios/{portfolio_id}/transactions/import/preview",
                content=csv_import_payload(),
                headers={"Content-Type": "text/csv"},
            ),
            await client.post(
                f"/portfolios/{portfolio_id}/transactions/import",
                content=csv_import_payload(),
                headers={"Content-Type": "text/csv"},
            ),
            await client.get(
                f"/portfolios/{portfolio_id}/analytics",
                params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
            ),
        )

    assert all(response.status_code == 404 for response in responses)
    assert all(
        response.json()["error"]["code"] == "portfolio_not_found"
        for response in responses
    )


@pytest.mark.anyio
async def test_generated_insight_persists_model_prompt_and_input_summary(
    database_engine: AsyncEngine,
) -> None:
    generator = FakeInsightGenerator(
        GeneratedInsight(
            summary=(
                "Historical metrics indicate material variability and "
                "single-security concentration."
            ),
            additional_limitations=("The observation window is limited.",),
        ),
        generator_name="deepseek",
        model_name="deepseek-v4-flash",
        prompt_version="deepseek-risk-summary-v1",
    )
    app = build_test_app(database_engine, generator)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await authenticate(client)
        portfolio = await client.post("/portfolios", json={"name": "Snapshot"})
        portfolio_id = portfolio.json()["id"]
        await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_payload()
        )
        response = await client.post(
            f"/portfolios/{portfolio_id}/insights",
            params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
        )

    session_factory = create_session_factory(database_engine)
    async with session_factory() as session:
        snapshot = await session.scalar(select(AnalysisSnapshotRecord))

    assert response.status_code == 200
    assert snapshot is not None
    assert snapshot.generator == "deepseek"
    assert snapshot.model_name == "deepseek-v4-flash"
    assert snapshot.prompt_version == "deepseek-risk-summary-v1"
    assert snapshot.summary == response.json()["summary"]
    assert snapshot.metrics["as_of"] == "2026-01-06"
    assert snapshot.metrics["asset_weights"] == [{"symbol": "DEMO", "weight": "1"}]
    assert snapshot.methodology["price_basis"] == "adjusted_close"
    assert snapshot.generated_at is not None


@pytest.mark.anyio
async def test_insight_history_reads_legacy_rc_rows_and_enforces_ownership(
    database_engine: AsyncEngine,
) -> None:
    app = build_test_app(database_engine)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await authenticate(client)
        portfolio = await client.post("/portfolios", json={"name": "History"})
        portfolio_id = portfolio.json()["id"]
        transaction = await client.post(
            f"/portfolios/{portfolio_id}/transactions", json=buy_payload()
        )
        assert transaction.status_code == 201
        generated = await client.post(
            f"/portfolios/{portfolio_id}/insights",
            params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
        )
        assert generated.status_code == 200

        session_factory = create_session_factory(database_engine)
        async with session_factory() as session:
            current = await session.scalar(
                select(AnalysisSnapshotRecord).where(
                    AnalysisSnapshotRecord.portfolio_id == UUID(portfolio_id)
                )
            )
            assert current is not None
            legacy_id = uuid4()
            legacy_generated_at = current.generated_at + timedelta(seconds=1)
            session.add(
                AnalysisSnapshotRecord(
                    id=legacy_id,
                    portfolio_id=UUID(portfolio_id),
                    as_of=current.as_of,
                    metrics=current.metrics,
                    methodology=current.methodology,
                    summary=None,
                    generator=None,
                    model_name=None,
                    prompt_version=None,
                    generated_at=legacy_generated_at,
                )
            )
            await session.commit()

        history = await client.get(
            f"/portfolios/{portfolio_id}/insights",
            params={"limit": 1, "offset": 0},
        )
        second_page = await client.get(
            f"/portfolios/{portfolio_id}/insights",
            params={"limit": 1, "offset": 1},
        )

        await authenticate(
            client,
            email="other@example.com",
            password="persistent other password",
        )
        forbidden = await client.get(f"/portfolios/{portfolio_id}/insights")

    assert history.status_code == 200
    assert history.json() == {
        "items": [
            {
                "id": str(legacy_id),
                "as_of": "2026-01-06",
                "metrics": current.metrics,
                "methodology": current.methodology,
                "summary": None,
                "generator": None,
                "model_name": None,
                "prompt_version": None,
                "generated_at": legacy_generated_at.isoformat().replace("+00:00", "Z"),
            }
        ],
        "total": 2,
        "limit": 1,
        "offset": 0,
    }
    assert second_page.status_code == 200
    assert second_page.json()["total"] == 2
    assert second_page.json()["items"][0]["generator"] == "deterministic_rules"
    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "portfolio_not_found"
