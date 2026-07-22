from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from portfolio_analytics_api.domain import (
    PriceBasis,
    ReturnType,
    RiskLevel,
    TransactionType,
)

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]
ExternalId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]
Symbol = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=32),
]
CurrencyCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    ),
]
EmailAddress = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]


class RegisterRequest(BaseModel):
    email: EmailAddress
    password: SecretStr = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailAddress
    password: SecretStr = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TransactionInput(BaseModel):
    external_id: ExternalId
    transaction_type: TransactionType
    occurred_at: datetime
    symbol: Symbol | None = None
    quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=28, decimal_places=12
    )
    unit_price: Decimal | None = Field(
        default=None, gt=0, max_digits=20, decimal_places=8
    )
    cash_amount: Decimal | None = Field(
        default=None, gt=0, max_digits=20, decimal_places=8
    )
    fees: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=8)

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @model_validator(mode="after")
    def payload_matches_transaction_type(self) -> Self:
        if self.transaction_type in {TransactionType.BUY, TransactionType.SELL}:
            if self.symbol is None or self.quantity is None or self.unit_price is None:
                raise ValueError(
                    "BUY and SELL require symbol, quantity, and unit_price"
                )
            if self.cash_amount is not None:
                raise ValueError("BUY and SELL must not include cash_amount")
        else:
            if self.cash_amount is None:
                raise ValueError("DEPOSIT and WITHDRAWAL require cash_amount")
            if any(
                value is not None
                for value in (self.symbol, self.quantity, self.unit_price)
            ):
                raise ValueError(
                    "DEPOSIT and WITHDRAWAL only accept cash_amount and fees"
                )
        return self


class CreatePortfolioRequest(BaseModel):
    name: NonEmptyString
    base_currency: CurrencyCode = "USD"

    @field_validator("base_currency", mode="before")
    @classmethod
    def normalize_base_currency(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
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
    base_currency: str


class MethodologyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annual_risk_free_rate: Decimal
    risk_free_rate_as_of: date
    risk_free_rate_assumption: str
    price_basis: PriceBasis
    return_type: ReturnType
    annualization_periods: int
    valuation_method: str
    cash_flow_policy: str
    fee_policy: str
    date_alignment_policy: str
    transaction_date_timezone: str


class AssetWeightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    market_value: Decimal
    weight: Decimal


class PortfolioAnalyticsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: date
    simple_return: float | None
    annualized_volatility: float | None
    max_drawdown: float | None
    sharpe_ratio: float | None
    portfolio_value: Decimal
    cash_balance: Decimal
    asset_weights: list[AssetWeightResponse]
    methodology: MethodologyResponse
    stale: bool


class PortfolioInsightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: date
    risk_level: RiskLevel
    summary: str
    key_factors: list[str]
    limitations: list[str]
    disclaimer: str
    generator: str
    model_name: str | None
    prompt_version: str
    stale: bool


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
