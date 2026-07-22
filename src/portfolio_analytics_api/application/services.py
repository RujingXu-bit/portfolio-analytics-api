from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from portfolio_analytics_api.application.errors import (
    PortfolioAnalyticsUnavailableError,
    PortfolioNotFoundError,
)
from portfolio_analytics_api.application.ports import (
    MarketDataProvider,
    PortfolioRepository,
)
from portfolio_analytics_api.domain import (
    AnalyticsMethodology,
    Portfolio,
    PortfolioAnalytics,
    Transaction,
    TransactionType,
    calculate_annualized_volatility,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_simple_returns,
)


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


class PortfolioService:
    def __init__(
        self,
        repository: PortfolioRepository,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory

    async def create(
        self,
        name: str,
        transactions: Sequence[NewTransaction],
    ) -> Portfolio:
        portfolio_id = self._id_factory()
        portfolio = Portfolio(
            id=portfolio_id,
            name=name,
            transactions=tuple(
                Transaction(
                    portfolio_id=portfolio_id,
                    external_id=transaction.external_id,
                    transaction_type=transaction.transaction_type,
                    occurred_at=transaction.occurred_at,
                    symbol=transaction.symbol,
                    quantity=transaction.quantity,
                    unit_price=transaction.unit_price,
                    cash_amount=transaction.cash_amount,
                    fees=transaction.fees,
                )
                for transaction in transactions
            ),
        )
        await self._repository.add(portfolio)
        return portfolio


class PortfolioAnalyticsService:
    def __init__(
        self,
        repository: PortfolioRepository,
        market_data_provider: MarketDataProvider,
        methodology: AnalyticsMethodology,
    ) -> None:
        self._repository = repository
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

        portfolio = await self._repository.get(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)

        symbols = {
            transaction.symbol.upper()
            for transaction in portfolio.transactions
            if transaction.transaction_type
            in {TransactionType.BUY, TransactionType.SELL}
            and transaction.symbol is not None
        }
        if len(symbols) != 1:
            raise PortfolioAnalyticsUnavailableError(
                "the W1.4 in-memory slice requires exactly one traded symbol"
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
