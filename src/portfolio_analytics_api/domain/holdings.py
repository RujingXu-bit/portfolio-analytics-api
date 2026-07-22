from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from portfolio_analytics_api.domain.models import (
    Position,
    Transaction,
    TransactionType,
)


class InvalidTransactionError(ValueError):
    """Raised when a transaction violates the deterministic ledger rules."""


def validate_transaction(transaction: Transaction) -> None:
    if not transaction.external_id.strip():
        raise InvalidTransactionError("external_id must not be blank")
    if transaction.occurred_at.tzinfo is None:
        raise InvalidTransactionError("occurred_at must include a timezone")
    if transaction.created_at is not None and transaction.created_at.tzinfo is None:
        raise InvalidTransactionError("created_at must include a timezone")
    _require_non_negative_finite(transaction.fees, "fees")

    if transaction.transaction_type in {TransactionType.BUY, TransactionType.SELL}:
        if transaction.symbol is None or not transaction.symbol.strip():
            raise InvalidTransactionError("BUY and SELL require symbol")
        if transaction.symbol != transaction.symbol.strip().upper():
            raise InvalidTransactionError("symbol must be normalized to uppercase")
        _require_positive_finite(transaction.quantity, "quantity")
        _require_positive_finite(transaction.unit_price, "unit_price")
        if transaction.cash_amount is not None:
            raise InvalidTransactionError("BUY and SELL must not include cash_amount")
        return

    if transaction.transaction_type in {
        TransactionType.DEPOSIT,
        TransactionType.WITHDRAWAL,
    }:
        if any(
            value is not None
            for value in (
                transaction.symbol,
                transaction.quantity,
                transaction.unit_price,
            )
        ):
            raise InvalidTransactionError(
                "DEPOSIT and WITHDRAWAL only accept cash_amount"
            )
        _require_positive_finite(transaction.cash_amount, "cash_amount")
        return

    raise InvalidTransactionError(
        f"unsupported transaction type: {transaction.transaction_type}"
    )


def derive_positions(transactions: Sequence[Transaction]) -> tuple[Position, ...]:
    quantities: dict[str, Decimal] = {}
    for transaction in transactions:
        validate_transaction(transaction)
    for transaction in sorted(transactions, key=_ledger_order):
        if transaction.transaction_type not in {
            TransactionType.BUY,
            TransactionType.SELL,
        }:
            continue

        assert transaction.symbol is not None
        assert transaction.quantity is not None
        current = quantities.get(transaction.symbol, Decimal(0))
        if transaction.transaction_type is TransactionType.BUY:
            updated = current + transaction.quantity
        else:
            updated = current - transaction.quantity
            if updated < 0:
                raise InvalidTransactionError(
                    f"SELL exceeds available position for {transaction.symbol}"
                )
        quantities[transaction.symbol] = updated

    return tuple(
        Position(symbol=symbol, quantity=quantity)
        for symbol, quantity in sorted(quantities.items())
        if quantity != 0
    )


def _ledger_order(transaction: Transaction) -> tuple[datetime, datetime, str]:
    created_at = transaction.created_at or transaction.occurred_at.astimezone(UTC)
    return transaction.occurred_at.astimezone(UTC), created_at, transaction.id.hex


def _require_positive_finite(value: Decimal | None, field_name: str) -> None:
    if value is None or not value.is_finite() or value <= 0:
        raise InvalidTransactionError(f"{field_name} must be finite and positive")


def _require_non_negative_finite(value: Decimal, field_name: str) -> None:
    if not value.is_finite() or value < 0:
        raise InvalidTransactionError(f"{field_name} must be finite and non-negative")
