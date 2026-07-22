from datetime import date
from typing import Protocol
from uuid import UUID

from portfolio_analytics_api.domain import Portfolio, PriceBar


class MarketDataProvider(Protocol):
    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[PriceBar, ...]: ...


class PortfolioRepository(Protocol):
    async def add(self, portfolio: Portfolio) -> None: ...

    async def get(self, portfolio_id: UUID) -> Portfolio | None: ...
