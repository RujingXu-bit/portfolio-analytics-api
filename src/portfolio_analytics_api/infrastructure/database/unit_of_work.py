from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_analytics_api.infrastructure.database.repositories import (
    PostgresAnalysisSnapshotRepository,
    PostgresPortfolioRepository,
    PostgresTransactionRepository,
    PostgresUserRepository,
)
from portfolio_analytics_api.infrastructure.database.session import AsyncSessionFactory


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: AsyncSessionFactory) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.users: PostgresUserRepository
        self.analysis_snapshots: PostgresAnalysisSnapshotRepository
        self.portfolios: PostgresPortfolioRepository
        self.transactions: PostgresTransactionRepository

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.users = PostgresUserRepository(self._session)
        self.analysis_snapshots = PostgresAnalysisSnapshotRepository(self._session)
        self.portfolios = PostgresPortfolioRepository(self._session)
        self.transactions = PostgresTransactionRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None:
            await self._session.rollback()
        await self._session.close()
        self._session = None

    async def commit(self) -> None:
        await self._require_session().commit()

    async def rollback(self) -> None:
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return self._session
