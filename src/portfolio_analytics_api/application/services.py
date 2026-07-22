from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from portfolio_analytics_api.application.errors import (
    PortfolioAnalyticsUnavailableError,
    PortfolioNotFoundError,
    TransactionIdempotencyConflictError,
)
from portfolio_analytics_api.application.ports import (
    MarketDataProvider,
    UnitOfWorkFactory,
)
from portfolio_analytics_api.domain import (
    AnalyticsMethodology,
    InvalidTransactionError,
    Portfolio,
    PortfolioAnalytics,
    Transaction,
    TransactionType,
    calculate_annualized_volatility,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_simple_returns,
    derive_positions,
    validate_transaction,
)

_QUANTITY_QUANTUM = Decimal("0.000000000001")
_MONEY_QUANTUM = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class NewTransaction:
    external_id: str
    transaction_type: TransactionType
    occurred_at: datetime
    symbol: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    cash_amount: Decimal | None = None
    fees: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class TransactionCreation:
    transaction: Transaction
    created: bool


class PortfolioService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._id_factory = id_factory

    async def create(
        self,
        name: str,
        base_currency: str,
    ) -> Portfolio:
        portfolio = Portfolio(
            id=self._id_factory(),
            name=name,
            base_currency=base_currency.strip().upper(),
        )
        async with self._unit_of_work_factory() as unit_of_work:
            await unit_of_work.portfolios.add(portfolio)
            await unit_of_work.commit()
        return portfolio

    async def get(self, portfolio_id: UUID) -> Portfolio:
        async with self._unit_of_work_factory() as unit_of_work:
            portfolio = await unit_of_work.portfolios.get(portfolio_id)
            if portfolio is None:
                raise PortfolioNotFoundError(portfolio_id)
            return portfolio


class PortfolioAnalyticsService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        market_data_provider: MarketDataProvider,
        methodology: AnalyticsMethodology,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._market_data_provider = market_data_provider
        self._methodology = methodology

    async def analyze(
        self,
        portfolio_id: UUID,
        start_date: date,
        end_date: date,
    ) -> PortfolioAnalytics:
        if start_date > end_date:
            raise PortfolioAnalyticsUnavailableError(
                "start_date must not be after end_date"
            )

        async with self._unit_of_work_factory() as unit_of_work:
            portfolio = await unit_of_work.portfolios.get(portfolio_id)
            if portfolio is None:
                raise PortfolioNotFoundError(portfolio_id)
            transactions = await unit_of_work.transactions.list_for_portfolio(
                portfolio_id
            )

        symbols = {
            transaction.symbol.upper()
            for transaction in transactions
            if transaction.transaction_type
            in {TransactionType.BUY, TransactionType.SELL}
            and transaction.symbol is not None
        }
        if len(symbols) != 1:
            raise PortfolioAnalyticsUnavailableError(
                "the current analytics scope requires exactly one traded symbol"
            )
        symbol = next(iter(symbols))

        price_bars = await self._market_data_provider.get_price_bars(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        if not price_bars:
            raise PortfolioAnalyticsUnavailableError(
                f"no price bars fall within the requested range for {symbol}"
            )

        ordered_bars = tuple(sorted(price_bars, key=lambda price_bar: price_bar.date))
        daily_returns = calculate_simple_returns(ordered_bars)
        simple_return = None
        if len(ordered_bars) > 1:
            simple_return = calculate_simple_returns(
                (ordered_bars[0], ordered_bars[-1])
            )[0]
        return PortfolioAnalytics(
            as_of=ordered_bars[-1].date,
            simple_return=simple_return,
            annualized_volatility=calculate_annualized_volatility(
                daily_returns,
                self._methodology.annualization_periods,
            ),
            max_drawdown=calculate_max_drawdown(ordered_bars),
            sharpe_ratio=calculate_sharpe_ratio(
                daily_returns,
                self._methodology.annual_risk_free_rate,
                self._methodology.annualization_periods,
            ),
            methodology=self._methodology,
        )


class TransactionService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._id_factory = id_factory
        self._clock = clock

    async def create(
        self,
        portfolio_id: UUID,
        new_transaction: NewTransaction,
    ) -> TransactionCreation:
        transaction = _build_transaction(
            portfolio_id=portfolio_id,
            new_transaction=new_transaction,
            transaction_id=self._id_factory(),
            created_at=self._clock(),
        )
        validate_transaction(transaction)

        async with self._unit_of_work_factory() as unit_of_work:
            portfolio = await unit_of_work.portfolios.get_for_update(portfolio_id)
            if portfolio is None:
                raise PortfolioNotFoundError(portfolio_id)

            existing = await unit_of_work.transactions.get_by_external_id(
                portfolio_id, transaction.external_id
            )
            if existing is not None:
                if _same_transaction_payload(existing, transaction):
                    return TransactionCreation(transaction=existing, created=False)
                raise TransactionIdempotencyConflictError(
                    portfolio_id, transaction.external_id
                )

            ledger = await unit_of_work.transactions.list_for_portfolio(portfolio_id)
            derive_positions((*ledger, transaction))
            await unit_of_work.transactions.add(transaction)
            await unit_of_work.commit()
            return TransactionCreation(transaction=transaction, created=True)

    async def list(self, portfolio_id: UUID) -> tuple[Transaction, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            portfolio = await unit_of_work.portfolios.get(portfolio_id)
            if portfolio is None:
                raise PortfolioNotFoundError(portfolio_id)
            return await unit_of_work.transactions.list_for_portfolio(portfolio_id)


def _build_transaction(
    *,
    portfolio_id: UUID,
    new_transaction: NewTransaction,
    transaction_id: UUID,
    created_at: datetime,
) -> Transaction:
    normalized_symbol = (
        new_transaction.symbol.strip().upper()
        if new_transaction.symbol is not None
        else None
    )
    occurred_at = new_transaction.occurred_at
    if occurred_at.tzinfo is not None:
        occurred_at = occurred_at.astimezone(UTC)
    return Transaction(
        id=transaction_id,
        portfolio_id=portfolio_id,
        external_id=new_transaction.external_id.strip(),
        transaction_type=new_transaction.transaction_type,
        occurred_at=occurred_at,
        created_at=created_at,
        symbol=normalized_symbol,
        quantity=_quantize_exact(
            new_transaction.quantity, _QUANTITY_QUANTUM, "quantity"
        ),
        unit_price=_quantize_exact(
            new_transaction.unit_price, _MONEY_QUANTUM, "unit_price"
        ),
        cash_amount=_quantize_exact(
            new_transaction.cash_amount, _MONEY_QUANTUM, "cash_amount"
        ),
        fees=_quantize_exact(new_transaction.fees, _MONEY_QUANTUM, "fees")
        or Decimal("0.00000000"),
    )


def _same_transaction_payload(left: Transaction, right: Transaction) -> bool:
    return (
        left.portfolio_id,
        left.external_id,
        left.transaction_type,
        left.occurred_at,
        left.symbol,
        left.quantity,
        left.unit_price,
        left.cash_amount,
        left.fees,
    ) == (
        right.portfolio_id,
        right.external_id,
        right.transaction_type,
        right.occurred_at,
        right.symbol,
        right.quantity,
        right.unit_price,
        right.cash_amount,
        right.fees,
    )


def _quantize_exact(
    value: Decimal | None,
    quantum: Decimal,
    field_name: str,
) -> Decimal | None:
    if value is None or not value.is_finite():
        return value
    try:
        normalized = value.quantize(quantum)
    except InvalidOperation as error:
        raise InvalidTransactionError(
            f"{field_name} exceeds supported precision"
        ) from error
    if normalized != value:
        raise InvalidTransactionError(f"{field_name} exceeds supported scale")
    return normalized
