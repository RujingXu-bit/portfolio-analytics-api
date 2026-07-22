from collections.abc import Mapping, Sequence
from datetime import date
from uuid import UUID

from portfolio_analytics_api.application import (
    MarketDataNotFoundError,
    PortfolioAlreadyExistsError,
)
from portfolio_analytics_api.domain import Portfolio, PriceBar


class InMemoryPortfolioRepository:
    def __init__(self) -> None:
        self._portfolios: dict[UUID, Portfolio] = {}

    async def add(self, portfolio: Portfolio) -> None:
        if portfolio.id in self._portfolios:
            raise PortfolioAlreadyExistsError(portfolio.id)
        self._portfolios[portfolio.id] = portfolio

    async def get(self, portfolio_id: UUID) -> Portfolio | None:
        return self._portfolios.get(portfolio_id)


class FakeMarketDataProvider:
    def __init__(self, price_bars_by_symbol: Mapping[str, Sequence[PriceBar]]) -> None:
        self._price_bars_by_symbol = {
            symbol.upper(): tuple(price_bars)
            for symbol, price_bars in price_bars_by_symbol.items()
        }

    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[PriceBar, ...]:
        normalized_symbol = symbol.upper()
        try:
            price_bars = self._price_bars_by_symbol[normalized_symbol]
        except KeyError as error:
            raise MarketDataNotFoundError(normalized_symbol) from error

        return tuple(
            sorted(
                (
                    price_bar
                    for price_bar in price_bars
                    if start_date <= price_bar.date <= end_date
                ),
                key=lambda price_bar: price_bar.date,
            )
        )
