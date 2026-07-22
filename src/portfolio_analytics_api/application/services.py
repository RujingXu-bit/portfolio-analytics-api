import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from portfolio_analytics_api.application.errors import (
    EmailAlreadyRegisteredError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    PortfolioAnalyticsUnavailableError,
    PortfolioNotFoundError,
    TransactionIdempotencyConflictError,
)
from portfolio_analytics_api.application.ports import (
    AccessTokenService,
    InsightGenerator,
    MarketDataProvider,
    PasswordHasher,
    UnitOfWorkFactory,
)
from portfolio_analytics_api.domain import (
    AnalysisSnapshot,
    AnalyticsMethodology,
    InsightInput,
    InvalidPortfolioValuationError,
    InvalidTransactionError,
    Portfolio,
    PortfolioAnalytics,
    PortfolioInsight,
    Transaction,
    TransactionType,
    User,
    build_portfolio_valuation,
    calculate_annualized_volatility,
    calculate_compounded_return,
    calculate_max_drawdown_from_returns,
    calculate_sharpe_ratio,
    derive_positions,
    generate_deterministic_insight,
    required_price_symbols,
    validate_generated_insight,
    validate_transaction,
)

_QUANTITY_QUANTUM = Decimal("0.000000000001")
_MONEY_QUANTUM = Decimal("0.00000001")
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AccessToken:
    value: str
    expires_in_seconds: int


class AuthenticationService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        password_hasher: PasswordHasher,
        access_token_service: AccessTokenService,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._password_hasher = password_hasher
        self._access_token_service = access_token_service
        self._id_factory = id_factory

    async def register(self, email: str, password: str) -> User:
        normalized_email = email.strip().lower()
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.users.get_by_email(normalized_email) is not None:
                raise EmailAlreadyRegisteredError(normalized_email)
            password_hash = await asyncio.to_thread(
                self._password_hasher.hash, password
            )
            user = User(
                id=self._id_factory(),
                email=normalized_email,
                password_hash=password_hash,
            )
            await unit_of_work.users.add(user)
            await unit_of_work.commit()
            return user

    async def login(self, email: str, password: str) -> AccessToken:
        normalized_email = email.strip().lower()
        async with self._unit_of_work_factory() as unit_of_work:
            user = await unit_of_work.users.get_by_email(normalized_email)
        if user is None:
            raise InvalidCredentialsError()
        password_matches = await asyncio.to_thread(
            self._password_hasher.verify, password, user.password_hash
        )
        if not password_matches:
            raise InvalidCredentialsError()
        return AccessToken(
            value=self._access_token_service.issue(user.id),
            expires_in_seconds=self._access_token_service.expires_in_seconds,
        )

    async def authenticate(self, token: str) -> User:
        user_id = self._access_token_service.verify(token)
        async with self._unit_of_work_factory() as unit_of_work:
            user = await unit_of_work.users.get(user_id)
        if user is None:
            raise InvalidAccessTokenError()
        return user


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


@dataclass(frozen=True, slots=True)
class PortfolioPage:
    items: tuple[Portfolio, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class AnalysisSnapshotPage:
    items: tuple[AnalysisSnapshot, ...]
    total: int
    limit: int
    offset: int


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
        owner_id: UUID,
        name: str,
        base_currency: str,
    ) -> Portfolio:
        portfolio = Portfolio(
            id=self._id_factory(),
            owner_id=owner_id,
            name=name,
            base_currency=base_currency.strip().upper(),
        )
        async with self._unit_of_work_factory() as unit_of_work:
            await unit_of_work.portfolios.add(portfolio)
            await unit_of_work.commit()
        return portfolio

    async def get(self, owner_id: UUID, portfolio_id: UUID) -> Portfolio:
        async with self._unit_of_work_factory() as unit_of_work:
            portfolio = await unit_of_work.portfolios.get(portfolio_id)
            if portfolio is None or portfolio.owner_id != owner_id:
                raise PortfolioNotFoundError(portfolio_id)
            return portfolio

    async def list(
        self,
        owner_id: UUID,
        limit: int,
        offset: int,
    ) -> PortfolioPage:
        async with self._unit_of_work_factory() as unit_of_work:
            items = await unit_of_work.portfolios.list_for_owner(
                owner_id,
                limit,
                offset,
            )
            total = await unit_of_work.portfolios.count_for_owner(owner_id)
        return PortfolioPage(items=items, total=total, limit=limit, offset=offset)


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
        owner_id: UUID,
        portfolio_id: UUID,
        start_date: date,
        end_date: date,
    ) -> PortfolioAnalytics:
        async with self._unit_of_work_factory() as unit_of_work:
            portfolio = await unit_of_work.portfolios.get(portfolio_id)
            if portfolio is None or portfolio.owner_id != owner_id:
                raise PortfolioNotFoundError(portfolio_id)
            transactions = await unit_of_work.transactions.list_for_portfolio(
                portfolio_id
            )

        if start_date > end_date:
            raise PortfolioAnalyticsUnavailableError(
                "start_date must not be after end_date"
            )

        try:
            symbols = required_price_symbols(transactions, start_date, end_date)
        except InvalidPortfolioValuationError as error:
            raise PortfolioAnalyticsUnavailableError(str(error)) from error
        if not symbols:
            raise PortfolioAnalyticsUnavailableError(
                "portfolio has no security holdings in the requested range"
            )

        market_data_results = await asyncio.gather(
            *(
                self._market_data_provider.get_price_bars(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                )
                for symbol in symbols
            )
        )
        try:
            valuation = build_portfolio_valuation(
                transactions=transactions,
                price_bars_by_symbol={
                    symbol: result.price_bars
                    for symbol, result in zip(symbols, market_data_results, strict=True)
                },
                start_date=start_date,
                end_date=end_date,
            )
        except InvalidPortfolioValuationError as error:
            raise PortfolioAnalyticsUnavailableError(str(error)) from error

        daily_returns = valuation.period_returns
        return PortfolioAnalytics(
            as_of=valuation.points[-1].date,
            simple_return=calculate_compounded_return(daily_returns),
            annualized_volatility=calculate_annualized_volatility(
                daily_returns,
                self._methodology.annualization_periods,
            ),
            max_drawdown=calculate_max_drawdown_from_returns(daily_returns),
            sharpe_ratio=calculate_sharpe_ratio(
                daily_returns,
                self._methodology.annual_risk_free_rate,
                self._methodology.annualization_periods,
            ),
            portfolio_value=valuation.portfolio_value,
            cash_balance=valuation.cash_balance,
            asset_weights=valuation.asset_weights,
            methodology=self._methodology,
            stale=any(result.stale for result in market_data_results),
        )


class PortfolioInsightService:
    def __init__(
        self,
        analytics_service: PortfolioAnalyticsService,
        unit_of_work_factory: UnitOfWorkFactory,
        insight_generator: InsightGenerator | None = None,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._analytics_service = analytics_service
        self._unit_of_work_factory = unit_of_work_factory
        self._insight_generator = insight_generator
        self._id_factory = id_factory
        self._clock = clock

    async def generate(
        self,
        owner_id: UUID,
        portfolio_id: UUID,
        start_date: date,
        end_date: date,
    ) -> PortfolioInsight:
        analytics = await self._analytics_service.analyze(
            owner_id=owner_id,
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
        )
        insight_input = _build_insight_input(analytics)
        insight = generate_deterministic_insight(analytics)
        if self._insight_generator is not None:
            try:
                generated = await self._insight_generator.generate(insight_input)
                validate_generated_insight(generated)
            except Exception as error:
                logger.warning(
                    "optional insight generator failed; using deterministic rules",
                    extra={"error_type": type(error).__name__},
                )
            else:
                insight = replace(
                    insight,
                    summary=generated.summary,
                    limitations=tuple(
                        dict.fromkeys(
                            (*insight.limitations, *generated.additional_limitations)
                        )
                    ),
                    generator=self._insight_generator.generator_name,
                    model_name=self._insight_generator.model_name,
                    prompt_version=self._insight_generator.prompt_version,
                )

        snapshot = AnalysisSnapshot(
            id=self._id_factory(),
            portfolio_id=portfolio_id,
            as_of=insight.as_of,
            metrics=_snapshot_metrics(insight_input),
            methodology=_snapshot_methodology(insight_input.methodology),
            summary=insight.summary,
            generator=insight.generator,
            model_name=insight.model_name,
            prompt_version=insight.prompt_version,
            generated_at=self._clock(),
        )
        async with self._unit_of_work_factory() as unit_of_work:
            await unit_of_work.analysis_snapshots.add(snapshot)
            await unit_of_work.commit()
        return insight

    async def list_snapshots(
        self,
        owner_id: UUID,
        portfolio_id: UUID,
        limit: int,
        offset: int,
    ) -> AnalysisSnapshotPage:
        async with self._unit_of_work_factory() as unit_of_work:
            portfolio = await unit_of_work.portfolios.get(portfolio_id)
            if portfolio is None or portfolio.owner_id != owner_id:
                raise PortfolioNotFoundError(portfolio_id)
            items = await unit_of_work.analysis_snapshots.list_for_portfolio(
                portfolio_id,
                limit,
                offset,
            )
            total = await unit_of_work.analysis_snapshots.count_for_portfolio(
                portfolio_id
            )
        return AnalysisSnapshotPage(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )


def _build_insight_input(analytics: PortfolioAnalytics) -> InsightInput:
    return InsightInput(
        as_of=analytics.as_of,
        simple_return=analytics.simple_return,
        annualized_volatility=analytics.annualized_volatility,
        max_drawdown=analytics.max_drawdown,
        sharpe_ratio=analytics.sharpe_ratio,
        asset_weights=analytics.asset_weights,
        methodology=analytics.methodology,
        stale=analytics.stale,
    )


def _snapshot_metrics(insight_input: InsightInput) -> dict[str, object]:
    return {
        "as_of": insight_input.as_of.isoformat(),
        "simple_return": insight_input.simple_return,
        "annualized_volatility": insight_input.annualized_volatility,
        "max_drawdown": insight_input.max_drawdown,
        "sharpe_ratio": insight_input.sharpe_ratio,
        "asset_weights": [
            {"symbol": weight.symbol, "weight": str(weight.weight)}
            for weight in insight_input.asset_weights
        ],
        "stale": insight_input.stale,
    }


def _snapshot_methodology(methodology: AnalyticsMethodology) -> dict[str, object]:
    return {
        "annual_risk_free_rate": str(methodology.annual_risk_free_rate),
        "risk_free_rate_as_of": methodology.risk_free_rate_as_of.isoformat(),
        "risk_free_rate_assumption": methodology.risk_free_rate_assumption,
        "price_basis": methodology.price_basis.value,
        "return_type": methodology.return_type.value,
        "annualization_periods": methodology.annualization_periods,
        "valuation_method": methodology.valuation_method,
        "cash_flow_policy": methodology.cash_flow_policy,
        "fee_policy": methodology.fee_policy,
        "date_alignment_policy": methodology.date_alignment_policy,
        "transaction_date_timezone": methodology.transaction_date_timezone,
    }


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
        owner_id: UUID,
        portfolio_id: UUID,
        new_transaction: NewTransaction,
    ) -> TransactionCreation:
        async with self._unit_of_work_factory() as unit_of_work:
            portfolio = await unit_of_work.portfolios.get_for_update(portfolio_id)
            if portfolio is None or portfolio.owner_id != owner_id:
                raise PortfolioNotFoundError(portfolio_id)

            transaction = _build_transaction(
                portfolio_id=portfolio_id,
                new_transaction=new_transaction,
                transaction_id=self._id_factory(),
                created_at=self._clock(),
            )
            validate_transaction(transaction)

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

    async def list(self, owner_id: UUID, portfolio_id: UUID) -> tuple[Transaction, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            portfolio = await unit_of_work.portfolios.get(portfolio_id)
            if portfolio is None or portfolio.owner_id != owner_id:
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
