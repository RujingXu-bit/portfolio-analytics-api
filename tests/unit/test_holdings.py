from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from portfolio_analytics_api.domain import (
    InvalidTransactionError,
    Transaction,
    TransactionType,
    derive_positions,
    validate_transaction,
)

PORTFOLIO_ID = UUID("00000000-0000-0000-0000-000000000001")


def transaction(
    transaction_id: int,
    transaction_type: TransactionType,
    *,
    occurred_at: datetime | None = None,
    created_at: datetime | None = None,
    symbol: str | None = None,
    quantity: str | None = None,
    unit_price: str | None = None,
    cash_amount: str | None = None,
    fees: str = "0",
) -> Transaction:
    return Transaction(
        id=UUID(int=transaction_id),
        portfolio_id=PORTFOLIO_ID,
        external_id=f"tx-{transaction_id}",
        transaction_type=transaction_type,
        occurred_at=occurred_at or datetime(2026, 1, transaction_id, tzinfo=UTC),
        created_at=created_at or datetime(2026, 2, transaction_id, tzinfo=UTC),
        symbol=symbol,
        quantity=Decimal(quantity) if quantity is not None else None,
        unit_price=Decimal(unit_price) if unit_price is not None else None,
        cash_amount=Decimal(cash_amount) if cash_amount is not None else None,
        fees=Decimal(fees),
    )


def test_holdings_replay_trades_and_ignore_cash_flows() -> None:
    ledger = (
        transaction(1, TransactionType.DEPOSIT, cash_amount="1000"),
        transaction(
            2,
            TransactionType.BUY,
            symbol="AAPL",
            quantity="2.500000000001",
            unit_price="100.12345678",
        ),
        transaction(
            3,
            TransactionType.SELL,
            symbol="AAPL",
            quantity="0.5",
            unit_price="110",
        ),
        transaction(4, TransactionType.WITHDRAWAL, cash_amount="10"),
    )

    positions = derive_positions(ledger)

    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == Decimal("2.000000000001")


def test_exact_sale_removes_position() -> None:
    positions = derive_positions(
        (
            transaction(
                1,
                TransactionType.BUY,
                symbol="AAPL",
                quantity="2",
                unit_price="100",
            ),
            transaction(
                2,
                TransactionType.SELL,
                symbol="AAPL",
                quantity="2",
                unit_price="101",
            ),
        )
    )

    assert positions == ()


def test_backdated_sale_is_rejected_when_holding_was_not_yet_available() -> None:
    with pytest.raises(InvalidTransactionError, match="exceeds available position"):
        derive_positions(
            (
                transaction(
                    2,
                    TransactionType.BUY,
                    occurred_at=datetime(2026, 1, 10, tzinfo=UTC),
                    symbol="AAPL",
                    quantity="1",
                    unit_price="100",
                ),
                transaction(
                    1,
                    TransactionType.SELL,
                    occurred_at=datetime(2026, 1, 5, tzinfo=UTC),
                    symbol="AAPL",
                    quantity="1",
                    unit_price="90",
                ),
            )
        )


def test_created_at_breaks_equal_occurrence_time_ties() -> None:
    occurred_at = datetime(2026, 1, 2, tzinfo=UTC)
    with pytest.raises(InvalidTransactionError, match="exceeds available position"):
        derive_positions(
            (
                transaction(
                    2,
                    TransactionType.BUY,
                    occurred_at=occurred_at,
                    created_at=datetime(2026, 1, 3, tzinfo=UTC),
                    symbol="AAPL",
                    quantity="1",
                    unit_price="100",
                ),
                transaction(
                    1,
                    TransactionType.SELL,
                    occurred_at=occurred_at,
                    created_at=datetime(2026, 1, 2, tzinfo=UTC),
                    symbol="AAPL",
                    quantity="1",
                    unit_price="100",
                ),
            )
        )


@pytest.mark.parametrize(
    ("invalid", "message"),
    [
        (
            transaction(
                1,
                TransactionType.BUY,
                symbol=None,
                quantity="1",
                unit_price="1",
            ),
            "require symbol",
        ),
        (
            transaction(
                1,
                TransactionType.BUY,
                symbol="aapl",
                quantity="1",
                unit_price="1",
            ),
            "normalized",
        ),
        (
            transaction(
                1,
                TransactionType.BUY,
                symbol="AAPL",
                quantity="NaN",
                unit_price="1",
            ),
            "quantity must be finite",
        ),
        (
            transaction(
                1,
                TransactionType.DEPOSIT,
                symbol="AAPL",
                cash_amount="10",
            ),
            "only accept cash_amount",
        ),
        (
            transaction(1, TransactionType.WITHDRAWAL, cash_amount=None),
            "cash_amount must be finite",
        ),
        (
            transaction(1, TransactionType.DEPOSIT, cash_amount="10", fees="-1"),
            "fees must be finite",
        ),
    ],
)
def test_invalid_transaction_shapes_are_rejected(
    invalid: Transaction, message: str
) -> None:
    with pytest.raises(InvalidTransactionError, match=message):
        validate_transaction(invalid)


def test_naive_timestamp_is_rejected() -> None:
    invalid = transaction(
        1,
        TransactionType.DEPOSIT,
        occurred_at=datetime(2026, 1, 2),
        cash_amount="10",
    )

    with pytest.raises(InvalidTransactionError, match="include a timezone"):
        validate_transaction(invalid)


def test_non_utc_aware_timestamp_is_valid() -> None:
    validate_transaction(
        transaction(
            1,
            TransactionType.DEPOSIT,
            occurred_at=datetime(2026, 1, 2, 9, tzinfo=timezone(timedelta(hours=2))),
            cash_amount="10",
        )
    )
