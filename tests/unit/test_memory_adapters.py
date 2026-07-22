from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from portfolio_analytics_api.application import (
    MarketDataNotFoundError,
    PortfolioAlreadyExistsError,
)
from portfolio_analytics_api.domain import Portfolio, PriceBar
from portfolio_analytics_api.infrastructure import (
    FakeMarketDataProvider,
    InMemoryPortfolioRepository,
)


@pytest.mark.anyio
async def test_in_memory_repository_stores_and_retrieves_portfolio() -> None:
    repository = InMemoryPortfolioRepository()
    portfolio = Portfolio(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        owner_id=UUID("00000000-0000-0000-0000-000000000002"),
        name="Long-term portfolio",
    )

    assert await repository.get(portfolio.id) is None

    await repository.add(portfolio)

    assert await repository.get(portfolio.id) is portfolio

    with pytest.raises(PortfolioAlreadyExistsError, match="already exists"):
        await repository.add(portfolio)


@pytest.mark.anyio
async def test_fake_provider_filters_dates_and_orders_fixed_prices() -> None:
    provider = FakeMarketDataProvider(
        {
            "demo": (
                PriceBar("DEMO", date(2026, 1, 6), Decimal("99")),
                PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),
                PriceBar("DEMO", date(2026, 1, 5), Decimal("110")),
            )
        }
    )

    result = await provider.get_price_bars(
        symbol="DeMo",
        start_date=date(2026, 1, 3),
        end_date=date(2026, 1, 6),
    )

    assert [price_bar.date for price_bar in result.price_bars] == [
        date(2026, 1, 5),
        date(2026, 1, 6),
    ]
    assert [price_bar.adjusted_close for price_bar in result.price_bars] == [
        Decimal("110"),
        Decimal("99"),
    ]
    assert result.stale is False


@pytest.mark.anyio
async def test_fake_provider_reports_unknown_symbol() -> None:
    provider = FakeMarketDataProvider({})

    with pytest.raises(MarketDataNotFoundError, match="UNKNOWN"):
        await provider.get_price_bars(
            symbol="unknown",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
