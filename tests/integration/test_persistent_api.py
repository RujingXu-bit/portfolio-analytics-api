from datetime import date
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from portfolio_analytics_api.api import create_app
from portfolio_analytics_api.application import UnitOfWork
from portfolio_analytics_api.core import Settings
from portfolio_analytics_api.domain import AnalyticsMethodology, PriceBar
from portfolio_analytics_api.infrastructure import FakeMarketDataProvider
from portfolio_analytics_api.infrastructure.database import (
    SqlAlchemyUnitOfWork,
    create_database_engine,
    create_session_factory,
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


def build_test_app(engine: AsyncEngine) -> FastAPI:
    session_factory = create_session_factory(engine)

    def unit_of_work_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return create_app(
        unit_of_work_factory=unit_of_work_factory,
        market_data_provider=FakeMarketDataProvider(
            {"DEMO": PRICES, "OTHER": OTHER_PRICES}
        ),
        methodology=METHODOLOGY,
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


@pytest.mark.anyio
async def test_all_endpoints_persist_across_app_and_engine_recreation(
    database_engine: AsyncEngine,
) -> None:
    first_app = build_test_app(database_engine)
    first_transport = httpx.ASGITransport(app=first_app)
    async with httpx.AsyncClient(
        transport=first_transport, base_url="http://test"
    ) as client:
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
async def test_persistent_api_values_multiple_assets(
    database_engine: AsyncEngine,
) -> None:
    app = build_test_app(database_engine)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
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
