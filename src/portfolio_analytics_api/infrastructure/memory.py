from collections.abc import Mapping, Sequence
from datetime import date
from types import TracebackType
from typing import Self
from uuid import UUID

from portfolio_analytics_api.application import (
    EmailAlreadyRegisteredError,
    MarketDataNotFoundError,
    MarketDataResult,
    PortfolioAlreadyExistsError,
)
from portfolio_analytics_api.domain import (
    AnalysisSnapshot,
    GeneratedInsight,
    InsightInput,
    Portfolio,
    PriceBar,
    Transaction,
    User,
)


class InMemoryStore:
    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}
        self.analysis_snapshots: list[AnalysisSnapshot] = []
        self.portfolios: dict[UUID, Portfolio] = {}
        self.transactions: list[Transaction] = []


class InMemoryUserRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, user: User) -> None:
        if any(existing.email == user.email for existing in self._store.users.values()):
            raise EmailAlreadyRegisteredError(user.email)
        self._store.users[user.id] = user

    async def get(self, user_id: UUID) -> User | None:
        return self._store.users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next(
            (user for user in self._store.users.values() if user.email == email),
            None,
        )


class InMemoryAnalysisSnapshotRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, snapshot: AnalysisSnapshot) -> None:
        self._store.analysis_snapshots.append(snapshot)

    async def list_for_portfolio(
        self,
        portfolio_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[AnalysisSnapshot, ...]:
        ordered = sorted(
            (
                snapshot
                for snapshot in self._store.analysis_snapshots
                if snapshot.portfolio_id == portfolio_id
            ),
            key=lambda snapshot: (snapshot.generated_at, snapshot.id.hex),
            reverse=True,
        )
        return tuple(ordered[offset : offset + limit])

    async def count_for_portfolio(self, portfolio_id: UUID) -> int:
        return sum(
            snapshot.portfolio_id == portfolio_id
            for snapshot in self._store.analysis_snapshots
        )


class InMemoryPortfolioRepository:
    def __init__(self, store: InMemoryStore | None = None) -> None:
        self._store = store or InMemoryStore()

    async def add(self, portfolio: Portfolio) -> None:
        if portfolio.id in self._store.portfolios:
            raise PortfolioAlreadyExistsError(portfolio.id)
        self._store.portfolios[portfolio.id] = portfolio
        self._store.transactions.extend(portfolio.transactions)

    async def get(self, portfolio_id: UUID) -> Portfolio | None:
        return self._store.portfolios.get(portfolio_id)

    async def get_for_update(self, portfolio_id: UUID) -> Portfolio | None:
        return await self.get(portfolio_id)

    async def list_for_owner(
        self,
        owner_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[Portfolio, ...]:
        ordered = [
            portfolio
            for portfolio in reversed(tuple(self._store.portfolios.values()))
            if portfolio.owner_id == owner_id
        ]
        return tuple(ordered[offset : offset + limit])

    async def count_for_owner(self, owner_id: UUID) -> int:
        return sum(
            portfolio.owner_id == owner_id
            for portfolio in self._store.portfolios.values()
        )


class InMemoryTransactionRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, transaction: Transaction) -> None:
        self._store.transactions.append(transaction)

    async def get_by_external_id(
        self, portfolio_id: UUID, external_id: str
    ) -> Transaction | None:
        return next(
            (
                transaction
                for transaction in self._store.transactions
                if transaction.portfolio_id == portfolio_id
                and transaction.external_id == external_id
            ),
            None,
        )

    async def list_for_portfolio(self, portfolio_id: UUID) -> tuple[Transaction, ...]:
        return tuple(
            sorted(
                (
                    transaction
                    for transaction in self._store.transactions
                    if transaction.portfolio_id == portfolio_id
                ),
                key=lambda transaction: (
                    transaction.occurred_at,
                    transaction.created_at or transaction.occurred_at,
                    transaction.id.hex,
                ),
            )
        )


class InMemoryUnitOfWork:
    def __init__(self, store: InMemoryStore) -> None:
        self.users = InMemoryUserRepository(store)
        self.analysis_snapshots = InMemoryAnalysisSnapshotRepository(store)
        self.portfolios = InMemoryPortfolioRepository(store)
        self.transactions = InMemoryTransactionRepository(store)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


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
    ) -> MarketDataResult:
        normalized_symbol = symbol.upper()
        try:
            price_bars = self._price_bars_by_symbol[normalized_symbol]
        except KeyError as error:
            raise MarketDataNotFoundError(normalized_symbol) from error

        return MarketDataResult(
            tuple(
                sorted(
                    (
                        price_bar
                        for price_bar in price_bars
                        if start_date <= price_bar.date <= end_date
                    ),
                    key=lambda price_bar: price_bar.date,
                )
            )
        )


class FakeInsightGenerator:
    def __init__(
        self,
        result: GeneratedInsight | Exception,
        *,
        generator_name: str = "fake",
        model_name: str = "fake-model",
        prompt_version: str = "fake-prompt-v1",
    ) -> None:
        self._result = result
        self._generator_name = generator_name
        self._model_name = model_name
        self._prompt_version = prompt_version
        self.inputs: list[InsightInput] = []

    @property
    def generator_name(self) -> str:
        return self._generator_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    async def generate(self, insight_input: InsightInput) -> GeneratedInsight:
        self.inputs.append(insight_input)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result
