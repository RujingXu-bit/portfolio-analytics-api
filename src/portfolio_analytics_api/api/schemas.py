from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from portfolio_analytics_api.domain import PriceBasis, ReturnType, TransactionType

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]


class TransactionInput(BaseModel):
    external_id: NonEmptyString
    transaction_type: TransactionType
    occurred_at: datetime
    symbol: str | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, gt=0)
    cash_amount: Decimal | None = Field(default=None, gt=0)
    fees: Decimal = Field(default=Decimal("0"), ge=0)


class CreatePortfolioRequest(BaseModel):
    name: NonEmptyString
    transactions: tuple[TransactionInput, ...] = ()


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    portfolio_id: UUID
    external_id: str
    transaction_type: TransactionType
    occurred_at: datetime
    symbol: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    cash_amount: Decimal | None
    fees: Decimal


class PortfolioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    transactions: tuple[TransactionResponse, ...]


class MethodologyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annual_risk_free_rate: Decimal
    risk_free_rate_as_of: date
    risk_free_rate_assumption: str
    price_basis: PriceBasis
    return_type: ReturnType
    annualization_periods: int


class PortfolioAnalyticsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: date
    simple_return: float | None
    annualized_volatility: float | None
    max_drawdown: float | None
    sharpe_ratio: float | None
    methodology: MethodologyResponse


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
