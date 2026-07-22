from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from portfolio_analytics_api.domain.analytics import InvalidPriceSeriesError
from portfolio_analytics_api.domain.holdings import validate_transaction
from portfolio_analytics_api.domain.models import (
    AssetWeight,
    PortfolioValuation,
    PortfolioValuePoint,
    PriceBar,
    Transaction,
    TransactionType,
)


class InvalidPortfolioValuationError(ValueError):
    """Raised when a transaction ledger cannot produce a valid valuation."""


def required_price_symbols(
    transactions: Sequence[Transaction],
    start_date: date,
    end_date: date,
) -> tuple[str, ...]:
    """Return symbols held at the start or traded during the requested interval."""
    _validate_date_range(start_date, end_date)
    positions: dict[str, Decimal] = {}
    required: set[str] = set()
    ordered_transactions = _ordered_transactions(transactions, end_date)
    for transaction in ordered_transactions:
        transaction_date = _transaction_date(transaction)
        if transaction_date >= start_date:
            continue
        _apply_position_change(positions, transaction)
    required.update(symbol for symbol, quantity in positions.items() if quantity != 0)
    required.update(
        transaction.symbol
        for transaction in ordered_transactions
        if _transaction_date(transaction) >= start_date
        and transaction.symbol is not None
    )
    return tuple(sorted(required))


def build_portfolio_valuation(
    transactions: Sequence[Transaction],
    price_bars_by_symbol: Mapping[str, Sequence[PriceBar]],
    start_date: date,
    end_date: date,
) -> PortfolioValuation:
    """Replay a ledger into end-of-day values without using future information."""
    _validate_date_range(start_date, end_date)
    symbols = required_price_symbols(transactions, start_date, end_date)
    if not symbols:
        raise InvalidPortfolioValuationError(
            "portfolio has no security holdings in the requested range"
        )

    prices_by_date = _validated_prices(
        symbols, price_bars_by_symbol, start_date, end_date
    )
    valuation_dates = tuple(
        sorted(
            {
                price_date
                for symbol_prices in prices_by_date.values()
                for price_date in symbol_prices
            }
        )
    )
    if not valuation_dates:
        raise InvalidPortfolioValuationError(
            "no market dates are available in the requested range"
        )

    ordered_transactions = _ordered_transactions(transactions, end_date)
    transaction_index = 0
    positions: dict[str, Decimal] = {}
    cash_balance = Decimal(0)
    latest_prices: dict[str, Decimal] = {}
    pending_external_flow = Decimal(0)
    points: list[PortfolioValuePoint] = []

    for valuation_date in valuation_dates:
        for symbol, symbol_prices in prices_by_date.items():
            current_price = symbol_prices.get(valuation_date)
            if current_price is not None:
                latest_prices[symbol] = current_price

        while transaction_index < len(ordered_transactions):
            transaction = ordered_transactions[transaction_index]
            if _transaction_date(transaction) > valuation_date:
                break
            cash_balance, external_flow = _apply_transaction(
                positions, cash_balance, transaction
            )
            pending_external_flow += external_flow
            transaction_index += 1

        active_positions = {
            symbol: quantity for symbol, quantity in positions.items() if quantity != 0
        }
        if any(symbol not in latest_prices for symbol in active_positions):
            continue

        asset_values = {
            symbol: quantity * latest_prices[symbol]
            for symbol, quantity in active_positions.items()
        }
        total_value = cash_balance + sum(asset_values.values(), start=Decimal(0))
        if total_value <= 0:
            continue

        points.append(
            PortfolioValuePoint(
                date=valuation_date,
                total_value=total_value,
                cash_balance=cash_balance,
                net_external_flow=pending_external_flow,
            )
        )
        pending_external_flow = Decimal(0)

    if not points:
        raise InvalidPortfolioValuationError(
            "portfolio has no positive valuatable balance in the requested range"
        )

    active_positions = {
        symbol: quantity for symbol, quantity in positions.items() if quantity != 0
    }
    missing_latest = sorted(set(active_positions) - set(latest_prices))
    if missing_latest:
        raise InvalidPortfolioValuationError(
            f"no usable price is available for active symbol {missing_latest[0]}"
        )

    latest_point = points[-1]
    latest_asset_values = {
        symbol: quantity * latest_prices[symbol]
        for symbol, quantity in active_positions.items()
    }
    asset_weights = tuple(
        AssetWeight(
            symbol=symbol,
            market_value=market_value,
            weight=market_value / latest_point.total_value,
        )
        for symbol, market_value in sorted(latest_asset_values.items())
    )
    return PortfolioValuation(
        points=tuple(points),
        period_returns=_cash_flow_adjusted_returns(points),
        portfolio_value=latest_point.total_value,
        cash_balance=latest_point.cash_balance,
        asset_weights=asset_weights,
    )


def _validated_prices(
    symbols: Sequence[str],
    price_bars_by_symbol: Mapping[str, Sequence[PriceBar]],
    start_date: date,
    end_date: date,
) -> dict[str, dict[date, Decimal]]:
    normalized_input = {
        symbol.upper(): tuple(price_bars)
        for symbol, price_bars in price_bars_by_symbol.items()
    }
    validated: dict[str, dict[date, Decimal]] = {}
    for symbol in symbols:
        symbol_prices: dict[date, Decimal] = {}
        for price_bar in normalized_input.get(symbol, ()):
            if price_bar.symbol.upper() != symbol:
                raise InvalidPriceSeriesError(
                    f"price bar symbol {price_bar.symbol} does not match {symbol}"
                )
            if (
                not price_bar.adjusted_close.is_finite()
                or price_bar.adjusted_close <= 0
            ):
                raise InvalidPriceSeriesError(
                    f"adjusted close must be finite and positive for {symbol}"
                )
            if not start_date <= price_bar.date <= end_date:
                continue
            if price_bar.date in symbol_prices:
                raise InvalidPriceSeriesError(
                    f"duplicate price date for {symbol}: {price_bar.date.isoformat()}"
                )
            symbol_prices[price_bar.date] = price_bar.adjusted_close
        if not symbol_prices:
            raise InvalidPortfolioValuationError(
                f"no price bars fall within the requested range for {symbol}"
            )
        validated[symbol] = symbol_prices
    return validated


def _apply_transaction(
    positions: dict[str, Decimal],
    cash_balance: Decimal,
    transaction: Transaction,
) -> tuple[Decimal, Decimal]:
    validate_transaction(transaction)
    external_flow = Decimal(0)
    if transaction.transaction_type is TransactionType.DEPOSIT:
        assert transaction.cash_amount is not None
        cash_balance += transaction.cash_amount - transaction.fees
        external_flow = transaction.cash_amount
    elif transaction.transaction_type is TransactionType.WITHDRAWAL:
        assert transaction.cash_amount is not None
        required_cash = transaction.cash_amount + transaction.fees
        if required_cash > cash_balance:
            raise InvalidPortfolioValuationError(
                "WITHDRAWAL exceeds the available cash balance"
            )
        cash_balance -= required_cash
        external_flow = -transaction.cash_amount
    elif transaction.transaction_type is TransactionType.BUY:
        assert transaction.quantity is not None
        assert transaction.unit_price is not None
        required_cash = transaction.quantity * transaction.unit_price + transaction.fees
        if required_cash > cash_balance:
            contribution = required_cash - cash_balance
            cash_balance += contribution
            external_flow = contribution
        cash_balance -= required_cash
        _apply_position_change(positions, transaction)
    else:
        assert transaction.transaction_type is TransactionType.SELL
        assert transaction.quantity is not None
        assert transaction.unit_price is not None
        _apply_position_change(positions, transaction)
        cash_balance += transaction.quantity * transaction.unit_price - transaction.fees

    if cash_balance < 0:
        raise InvalidPortfolioValuationError(
            "transaction fees exceed the available cash balance"
        )
    return cash_balance, external_flow


def _apply_position_change(
    positions: dict[str, Decimal], transaction: Transaction
) -> None:
    if transaction.transaction_type not in {
        TransactionType.BUY,
        TransactionType.SELL,
    }:
        return
    assert transaction.symbol is not None
    assert transaction.quantity is not None
    current = positions.get(transaction.symbol, Decimal(0))
    if transaction.transaction_type is TransactionType.BUY:
        positions[transaction.symbol] = current + transaction.quantity
        return
    updated = current - transaction.quantity
    if updated < 0:
        raise InvalidPortfolioValuationError(
            f"SELL exceeds available position for {transaction.symbol}"
        )
    positions[transaction.symbol] = updated


def _cash_flow_adjusted_returns(
    points: Sequence[PortfolioValuePoint],
) -> tuple[float, ...]:
    returns: list[float] = []
    for previous, current in zip(points, points[1:], strict=False):
        if previous.total_value <= 0:
            raise InvalidPortfolioValuationError(
                "portfolio value must remain positive before calculating returns"
            )
        adjusted_value = current.total_value - current.net_external_flow
        if adjusted_value <= 0:
            raise InvalidPortfolioValuationError(
                "cash-flow-adjusted portfolio value must remain positive"
            )
        returns.append(float(adjusted_value / previous.total_value - Decimal(1)))
    return tuple(returns)


def _ordered_transactions(
    transactions: Sequence[Transaction], end_date: date
) -> tuple[Transaction, ...]:
    included: list[Transaction] = []
    for transaction in transactions:
        validate_transaction(transaction)
        if _transaction_date(transaction) <= end_date:
            included.append(transaction)
    return tuple(sorted(included, key=_ledger_order))


def _transaction_date(transaction: Transaction) -> date:
    return transaction.occurred_at.astimezone(UTC).date()


def _ledger_order(transaction: Transaction) -> tuple[datetime, datetime, str]:
    created_at = transaction.created_at or transaction.occurred_at.astimezone(UTC)
    return transaction.occurred_at.astimezone(UTC), created_at, transaction.id.hex


def _validate_date_range(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise InvalidPortfolioValuationError("start_date must not be after end_date")
