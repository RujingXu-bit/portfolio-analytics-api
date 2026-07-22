from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"


@dataclass(frozen=True, slots=True)
class PriceBar:
    symbol: str
    date: date
    adjusted_close: Decimal


@dataclass(frozen=True, slots=True)
class Transaction:
    portfolio_id: UUID
    external_id: str
    transaction_type: TransactionType
    occurred_at: datetime
    symbol: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    cash_amount: Decimal | None = None
    fees: Decimal = Decimal("0")
    id: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Portfolio:
    id: UUID
    name: str
    base_currency: str = "USD"
    owner_id: UUID | None = None
    transactions: tuple[Transaction, ...] = ()


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    quantity: Decimal


class PriceBasis(StrEnum):
    ADJUSTED_CLOSE = "adjusted_close"


class ReturnType(StrEnum):
    SIMPLE = "simple"


@dataclass(frozen=True, slots=True)
class AnalyticsMethodology:
    annual_risk_free_rate: Decimal
    risk_free_rate_as_of: date
    risk_free_rate_assumption: str
    price_basis: PriceBasis = PriceBasis.ADJUSTED_CLOSE
    return_type: ReturnType = ReturnType.SIMPLE
    annualization_periods: int = 252


@dataclass(frozen=True, slots=True)
class PortfolioAnalytics:
    as_of: date
    simple_return: float | None
    annualized_volatility: float | None
    max_drawdown: float | None
    sharpe_ratio: float | None
    methodology: AnalyticsMethodology
    stale: bool = False
