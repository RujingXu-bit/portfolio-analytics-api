from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import TracebackType
from typing import Self
from uuid import UUID

import pytest

from portfolio_analytics_api.application import (
    NewTransaction,
    PortfolioNotFoundError,
    PortfolioRepository,
    TransactionIdempotencyConflictError,
    TransactionRepository,
    TransactionService,
    UnitOfWork,
)
from portfolio_analytics_api.domain import (
    InvalidTransactionError,
    Portfolio,
    Transaction,
    TransactionType,
)

PORTFOLIO_ID = UUID("00000000-0000-0000-0000-000000000001")
TRANSACTION_ID = UUID("00000000-0000-0000-0000-000000000002")
CREATED_AT = datetime(2026, 1, 20, tzinfo=UTC)


class FakePortfolioRepository:
    def __init__(self, portfolios: dict[UUID, Portfolio]) -> None:
        self._portfolios = portfolios

    async def add(self, portfolio: Portfolio) -> None:
        self._portfolios[portfolio.id] = portfolio

    async def get(self, portfolio_id: UUID) -> Portfolio | None:
        return self._portfolios.get(portfolio_id)

    async def get_for_update(self, portfolio_id: UUID) -> Portfolio | None:
        return await self.get(portfolio_id)


class FakeTransactionRepository:
    def __init__(self, transactions: list[Transaction]) -> None:
        self._transactions = transactions

    async def add(self, transaction: Transaction) -> None:
        self._transactions.append(transaction)

    async def get_by_external_id(
        self, portfolio_id: UUID, external_id: str
    ) -> Transaction | None:
        return next(
            (
                transaction
                for transaction in self._transactions
                if transaction.portfolio_id == portfolio_id
                and transaction.external_id == external_id
            ),
            None,
        )

    async def list_for_portfolio(self, portfolio_id: UUID) -> tuple[Transaction, ...]:
        return tuple(
            transaction
            for transaction in self._transactions
            if transaction.portfolio_id == portfolio_id
        )


class FakeUnitOfWork:
    def __init__(
        self,
        portfolios: dict[UUID, Portfolio],
        transactions: list[Transaction],
        commits: list[bool],
    ) -> None:
        self.portfolios: PortfolioRepository = FakePortfolioRepository(portfolios)
        self.transactions: TransactionRepository = FakeTransactionRepository(
            transactions
        )
        self._commits = commits

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
        self._commits.append(True)

    async def rollback(self) -> None:
        return None


def service_fixture() -> tuple[
    TransactionService, list[Transaction], list[bool], Callable[[], UnitOfWork]
]:
    portfolios = {PORTFOLIO_ID: Portfolio(PORTFOLIO_ID, "Test")}
    transactions: list[Transaction] = []
    commits: list[bool] = []

    def unit_of_work_factory() -> UnitOfWork:
        return FakeUnitOfWork(portfolios, transactions, commits)

    service = TransactionService(
        unit_of_work_factory,
        id_factory=lambda: TRANSACTION_ID,
        clock=lambda: CREATED_AT,
    )
    return service, transactions, commits, unit_of_work_factory


def buy(*, external_id: str = "broker-001", quantity: str = "2") -> NewTransaction:
    return NewTransaction(
        external_id=external_id,
        transaction_type=TransactionType.BUY,
        occurred_at=datetime(2026, 1, 2, 11, tzinfo=timezone(timedelta(hours=2))),
        symbol=" aapl ",
        quantity=Decimal(quantity),
        unit_price=Decimal("100.12345678"),
        fees=Decimal("0.25"),
    )


@pytest.mark.anyio
async def test_create_normalizes_and_commits_transaction() -> None:
    service, transactions, commits, _factory = service_fixture()

    result = await service.create(PORTFOLIO_ID, buy())

    assert result.created is True
    assert result.transaction.id == TRANSACTION_ID
    assert result.transaction.symbol == "AAPL"
    assert result.transaction.occurred_at == datetime(2026, 1, 2, 9, tzinfo=UTC)
    assert transactions == [result.transaction]
    assert commits == [True]


@pytest.mark.anyio
async def test_identical_retry_returns_existing_without_second_commit() -> None:
    service, transactions, commits, _factory = service_fixture()

    first = await service.create(PORTFOLIO_ID, buy())
    second = await service.create(PORTFOLIO_ID, buy())

    assert first.created is True
    assert second.created is False
    assert second.transaction is first.transaction
    assert len(transactions) == 1
    assert commits == [True]


@pytest.mark.anyio
async def test_same_external_id_with_different_payload_conflicts() -> None:
    service, transactions, _commits, _factory = service_fixture()
    await service.create(PORTFOLIO_ID, buy())

    with pytest.raises(TransactionIdempotencyConflictError, match="different"):
        await service.create(PORTFOLIO_ID, buy(quantity="3"))

    assert len(transactions) == 1


@pytest.mark.anyio
async def test_oversell_is_rejected_without_write() -> None:
    service, transactions, commits, _factory = service_fixture()
    sell = NewTransaction(
        external_id="sell-001",
        transaction_type=TransactionType.SELL,
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        symbol="AAPL",
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
    )

    with pytest.raises(InvalidTransactionError, match="exceeds available position"):
        await service.create(PORTFOLIO_ID, sell)

    assert transactions == []
    assert commits == []


@pytest.mark.anyio
async def test_missing_portfolio_is_reported() -> None:
    _service, _transactions, _commits, factory = service_fixture()
    service = TransactionService(factory)

    with pytest.raises(PortfolioNotFoundError):
        await service.create(UUID(int=999), buy())
