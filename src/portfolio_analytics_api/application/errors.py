from uuid import UUID


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
