from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from portfolio_analytics_api.application import (
    NewTransaction,
    PortfolioNotFoundError,
    TransactionImportCandidate,
    TransactionImportIssue,
    TransactionImportRowStatus,
    TransactionImportService,
    TransactionService,
    UnitOfWork,
)
from portfolio_analytics_api.domain import Portfolio, TransactionType
from portfolio_analytics_api.infrastructure import InMemoryStore, InMemoryUnitOfWork

OWNER_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_ID = UUID("00000000-0000-0000-0000-000000000002")
PORTFOLIO_ID = UUID("00000000-0000-0000-0000-000000000003")
CREATED_AT = datetime(2026, 1, 20, tzinfo=UTC)


def _new_transaction(
    external_id: str,
    transaction_type: TransactionType,
    *,
    quantity: str | None = None,
) -> NewTransaction:
    if transaction_type is TransactionType.DEPOSIT:
        return NewTransaction(
            external_id=external_id,
            transaction_type=transaction_type,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            cash_amount=Decimal("1000"),
        )
    return NewTransaction(
        external_id=external_id,
        transaction_type=transaction_type,
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        symbol="AAPL",
        quantity=Decimal(quantity or "2"),
        unit_price=Decimal("100"),
    )


def _candidates() -> tuple[TransactionImportCandidate, ...]:
    buy = _new_transaction("buy-1", TransactionType.BUY)
    return (
        TransactionImportCandidate(
            2, "deposit-1", _new_transaction("deposit-1", TransactionType.DEPOSIT)
        ),
        TransactionImportCandidate(3, "buy-1", buy),
        TransactionImportCandidate(4, "buy-1", buy),
        TransactionImportCandidate(
            5,
            "buy-1",
            _new_transaction("buy-1", TransactionType.BUY, quantity="3"),
        ),
        TransactionImportCandidate(
            6,
            "sell-1",
            _new_transaction("sell-1", TransactionType.SELL, quantity="3"),
        ),
        TransactionImportCandidate(
            7,
            "bad-row",
            None,
            (
                TransactionImportIssue(
                    code="invalid_field",
                    field="occurred_at",
                    message="Input should be a valid datetime",
                ),
            ),
        ),
    )


def _service(
    parser: Callable[[bytes], tuple[TransactionImportCandidate, ...]],
) -> tuple[TransactionImportService, InMemoryStore]:
    store = InMemoryStore()
    store.portfolios[PORTFOLIO_ID] = Portfolio(
        id=PORTFOLIO_ID,
        owner_id=OWNER_ID,
        name="Import",
    )

    def unit_of_work_factory() -> UnitOfWork:
        return InMemoryUnitOfWork(store)

    ids = iter(UUID(int=value) for value in range(100, 200))
    transaction_service = TransactionService(
        unit_of_work_factory,
        id_factory=lambda: next(ids),
        clock=lambda: CREATED_AT,
    )
    return (
        TransactionImportService(
            unit_of_work_factory,
            transaction_service,
            parser,
            id_factory=lambda: next(ids),
            clock=lambda: CREATED_AT,
        ),
        store,
    )


@pytest.mark.anyio
async def test_preview_is_write_free_and_explains_every_row() -> None:
    service, store = _service(lambda _data: _candidates())

    preview = await service.preview(OWNER_ID, PORTFOLIO_ID, b"ignored")

    assert (preview.total_rows, preview.ready_rows, preview.replay_rows) == (6, 2, 1)
    assert preview.invalid_rows == 3
    assert [row.status for row in preview.rows] == [
        TransactionImportRowStatus.READY,
        TransactionImportRowStatus.READY,
        TransactionImportRowStatus.REPLAY,
        TransactionImportRowStatus.INVALID,
        TransactionImportRowStatus.INVALID,
        TransactionImportRowStatus.INVALID,
    ]
    assert preview.rows[3].issues[0].code == "idempotency_conflict"
    assert preview.rows[4].issues[0].code == "invalid_ledger"
    assert preview.rows[5].issues[0].field == "occurred_at"
    assert store.transactions == []


@pytest.mark.anyio
async def test_commit_partially_succeeds_and_retries_idempotently() -> None:
    service, store = _service(lambda _data: _candidates())

    first = await service.commit(OWNER_ID, PORTFOLIO_ID, b"ignored")
    second = await service.commit(OWNER_ID, PORTFOLIO_ID, b"ignored")

    assert (first.total_rows, first.created_rows, first.replayed_rows) == (6, 2, 1)
    assert first.failed_rows == 3
    assert [row.status for row in first.rows] == [
        TransactionImportRowStatus.CREATED,
        TransactionImportRowStatus.CREATED,
        TransactionImportRowStatus.REPLAYED,
        TransactionImportRowStatus.FAILED,
        TransactionImportRowStatus.FAILED,
        TransactionImportRowStatus.FAILED,
    ]
    assert (second.created_rows, second.replayed_rows, second.failed_rows) == (0, 3, 3)
    assert {transaction.external_id for transaction in store.transactions} == {
        "deposit-1",
        "buy-1",
    }


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["preview", "commit"])
async def test_import_checks_ownership_before_parsing(operation: str) -> None:
    def parser(_data: bytes) -> tuple[TransactionImportCandidate, ...]:
        raise AssertionError("parser must not run before ownership check")

    service, _store = _service(parser)

    with pytest.raises(PortfolioNotFoundError):
        await getattr(service, operation)(OTHER_ID, PORTFOLIO_ID, b"secret csv")
