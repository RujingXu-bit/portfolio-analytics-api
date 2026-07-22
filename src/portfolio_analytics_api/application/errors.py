from uuid import UUID


class EmailAlreadyRegisteredError(ValueError):
    def __init__(self, email: str) -> None:
        super().__init__(f"email {email!r} is already registered")


class AuthenticationError(PermissionError):
    """Base error for failures that share one safe HTTP response."""


class InvalidCredentialsError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__("authentication failed")


class InvalidAccessTokenError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__("authentication failed")


class InsightGenerationError(RuntimeError):
    """Raised when an optional external insight generator cannot return safe output."""


class RateLimitExceededError(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("request rate limit exceeded")


class PortfolioNotFoundError(LookupError):
    def __init__(self, portfolio_id: UUID) -> None:
        super().__init__(f"portfolio {portfolio_id} was not found")


class PortfolioAlreadyExistsError(ValueError):
    def __init__(self, portfolio_id: UUID) -> None:
        super().__init__(f"portfolio {portfolio_id} already exists")


class PortfolioAnalyticsUnavailableError(ValueError):
    """Raised when the temporary slice cannot analyze a portfolio."""


class MarketDataNotFoundError(LookupError):
    def __init__(self, symbol: str) -> None:
        super().__init__(f"no market data is available for symbol {symbol}")


class MarketDataInvalidResponseError(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(f"market data provider returned invalid data: {message}")


class MarketDataRetryableError(RuntimeError):
    """Base class for transient market-data failures."""


class MarketDataRateLimitError(MarketDataRetryableError):
    def __init__(self) -> None:
        super().__init__("market data provider rate limit was reached")


class MarketDataUnavailableError(MarketDataRetryableError):
    def __init__(self) -> None:
        super().__init__("market data provider is temporarily unavailable")


class MarketDataTimeoutError(MarketDataRetryableError):
    def __init__(self) -> None:
        super().__init__("market data provider request timed out")


class TransactionIdempotencyConflictError(ValueError):
    def __init__(self, portfolio_id: UUID, external_id: str) -> None:
        super().__init__(
            f"external_id {external_id!r} is already used in portfolio {portfolio_id} "
            "with different transaction data"
        )
