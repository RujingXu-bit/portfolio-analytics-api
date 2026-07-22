from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from types import TracebackType
from typing import Protocol
from uuid import UUID

from portfolio_analytics_api.domain import (
    AnalysisSnapshot,
    GeneratedInsight,
    InsightInput,
    Portfolio,
    PriceBar,
    Transaction,
    User,
)


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


class UserRepository(Protocol):
    async def add(self, user: User) -> None: ...

    async def get(self, user_id: UUID) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class AccessTokenService(Protocol):
    @property
    def expires_in_seconds(self) -> int: ...

    def issue(self, user_id: UUID) -> str: ...

    def verify(self, token: str) -> UUID: ...


class InsightGenerator(Protocol):
    @property
    def generator_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def prompt_version(self) -> str: ...

    async def generate(self, insight_input: InsightInput) -> GeneratedInsight: ...


class AnalysisSnapshotRepository(Protocol):
    async def add(self, snapshot: AnalysisSnapshot) -> None: ...


class UnitOfWork(Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def portfolios(self) -> PortfolioRepository: ...

    @property
    def transactions(self) -> TransactionRepository: ...

    @property
    def analysis_snapshots(self) -> AnalysisSnapshotRepository: ...

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
