from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from types import TracebackType
from typing import Protocol
from uuid import UUID

from portfolio_analytics_api.domain import Portfolio, PriceBar, Transaction


@dataclass(frozen=True, slots=True)
class MarketDataResult:
    price_bars: tuple[PriceBar, ...]
    stale: bool = False


class MarketDataProvider(Protocol):
    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> MarketDataResult: ...


class PortfolioRepository(Protocol):
    async def add(self, portfolio: Portfolio) -> None: ...

    async def get(self, portfolio_id: UUID) -> Portfolio | None: ...

    async def get_for_update(self, portfolio_id: UUID) -> Portfolio | None: ...


class TransactionRepository(Protocol):
    async def add(self, transaction: Transaction) -> None: ...

    async def get_by_external_id(
        self, portfolio_id: UUID, external_id: str
    ) -> Transaction | None: ...

    async def list_for_portfolio(
        self, portfolio_id: UUID
    ) -> tuple[Transaction, ...]: ...


class UnitOfWork(Protocol):
    @property
    def portfolios(self) -> PortfolioRepository: ...

    @property
    def transactions(self) -> TransactionRepository: ...

    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
