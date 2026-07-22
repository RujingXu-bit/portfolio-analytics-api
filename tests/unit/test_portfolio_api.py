from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from math import sqrt
from uuid import UUID

import httpx
import pytest

from portfolio_analytics_api.api import create_app
from portfolio_analytics_api.application import PortfolioAlreadyExistsError
from portfolio_analytics_api.domain import AnalyticsMethodology, Portfolio, PriceBar
from portfolio_analytics_api.infrastructure import (
    FakeMarketDataProvider,
    InMemoryPortfolioRepository,
)


class DuplicatePortfolioRepository:
    async def add(self, portfolio: Portfolio) -> None:
        raise PortfolioAlreadyExistsError(portfolio.id)

    async def get(self, _portfolio_id: UUID) -> Portfolio | None:
        return None


@asynccontextmanager
async def api_client(
    price_bars_by_symbol: dict[str, tuple[PriceBar, ...]],
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        portfolio_repository=InMemoryPortfolioRepository(),
        market_data_provider=FakeMarketDataProvider(price_bars_by_symbol),
        methodology=AnalyticsMethodology(
            annual_risk_free_rate=Decimal("0"),
            risk_free_rate_as_of=date(2026, 1, 1),
            risk_free_rate_assumption="Fixed offline test rate.",
        ),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield client


def buy_transaction(
    symbol: str = "DEMO", external_id: str = "buy-001"
) -> dict[str, str]:
    return {
        "external_id": external_id,
        "transaction_type": "BUY",
        "occurred_at": "2026-01-02T09:00:00Z",
        "symbol": symbol,
        "quantity": "2",
        "unit_price": "100",
        "fees": "0.25",
    }


async def create_portfolio(
    client: httpx.AsyncClient,
    transactions: list[dict[str, str]],
) -> str:
    response = await client.post(
        "/portfolios",
        json={"name": " Offline demo ", "transactions": transactions},
    )

    assert response.status_code == 201
    body = response.json()
    UUID(body["id"])
    assert body["name"] == "Offline demo"
    assert body["transactions"][0]["portfolio_id"] == body["id"]
    return str(body["id"])


@pytest.mark.anyio
async def test_fixed_transactions_and_prices_return_all_metrics() -> None:
    prices = (
        PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),
        PriceBar("DEMO", date(2026, 1, 5), Decimal("110")),
        PriceBar("DEMO", date(2026, 1, 6), Decimal("99")),
    )
    async with api_client({"DEMO": prices}) as client:
        portfolio_id = await create_portfolio(client, [buy_transaction()])

        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-02", "end_date": "2026-01-06"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["as_of"] == "2026-01-06"
    assert body["simple_return"] == pytest.approx(-0.01)
    assert body["annualized_volatility"] == pytest.approx(0.2 / sqrt(2) * sqrt(252))
    assert body["max_drawdown"] == pytest.approx(-0.1)
    assert body["sharpe_ratio"] == pytest.approx(0.0)
    assert body["methodology"] == {
        "annual_risk_free_rate": "0",
        "risk_free_rate_as_of": "2026-01-01",
        "risk_free_rate_assumption": "Fixed offline test rate.",
        "price_basis": "adjusted_close",
        "return_type": "simple",
        "annualization_periods": 252,
    }


@pytest.mark.anyio
async def test_single_price_has_only_defined_drawdown() -> None:
    prices = (PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),)
    async with api_client({"DEMO": prices}) as client:
        portfolio_id = await create_portfolio(client, [buy_transaction()])
        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-02", "end_date": "2026-01-02"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["simple_return"] is None
    assert body["annualized_volatility"] is None
    assert body["max_drawdown"] == 0.0
    assert body["sharpe_ratio"] is None


@pytest.mark.anyio
async def test_missing_portfolio_has_stable_not_found_error() -> None:
    async with api_client({}) as client:
        response = await client.get(
            "/portfolios/00000000-0000-0000-0000-000000000001/analytics",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_not_found"


@pytest.mark.anyio
async def test_temporary_slice_rejects_multiple_symbols() -> None:
    async with api_client({}) as client:
        portfolio_id = await create_portfolio(
            client,
            [buy_transaction(), buy_transaction("OTHER", "buy-002")],
        )
        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "analytics_unavailable",
            "message": "the W1.4 in-memory slice requires exactly one traded symbol",
        }
    }


@pytest.mark.anyio
async def test_unknown_symbol_has_stable_market_data_error() -> None:
    async with api_client({}) as client:
        portfolio_id = await create_portfolio(
            client, [buy_transaction(symbol="UNKNOWN")]
        )
        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "market_data_not_found"


@pytest.mark.anyio
async def test_empty_requested_range_has_stable_analytics_error() -> None:
    prices = (PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),)
    async with api_client({"DEMO": prices}) as client:
        portfolio_id = await create_portfolio(client, [buy_transaction()])
        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-02-01", "end_date": "2026-02-28"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "analytics_unavailable"


@pytest.mark.anyio
async def test_invalid_date_range_has_stable_analytics_error() -> None:
    async with api_client({}) as client:
        portfolio_id = await create_portfolio(client, [buy_transaction()])
        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-02-01", "end_date": "2026-01-01"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "analytics_unavailable"


@pytest.mark.anyio
async def test_request_validation_uses_stable_error_shape() -> None:
    async with api_client({}) as client:
        response = await client.post(
            "/portfolios",
            json={"name": "   ", "transactions": []},
        )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "request validation failed",
        }
    }


@pytest.mark.anyio
async def test_repository_conflict_has_stable_error() -> None:
    app = create_app(
        portfolio_repository=DuplicatePortfolioRepository(),
        market_data_provider=FakeMarketDataProvider({}),
        methodology=AnalyticsMethodology(
            annual_risk_free_rate=Decimal("0"),
            risk_free_rate_as_of=date(2026, 1, 1),
            risk_free_rate_assumption="Fixed offline test rate.",
        ),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/portfolios",
            json={"name": "Conflict", "transactions": []},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "portfolio_conflict"


@pytest.mark.anyio
async def test_invalid_price_series_has_stable_error() -> None:
    prices = (
        PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),
        PriceBar("DEMO", date(2026, 1, 2), Decimal("101")),
    )
    async with api_client({"DEMO": prices}) as client:
        portfolio_id = await create_portfolio(client, [buy_transaction()])
        response = await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_price_series"
