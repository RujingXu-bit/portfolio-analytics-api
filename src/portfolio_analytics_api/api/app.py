from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from portfolio_analytics_api.api.routes import build_portfolio_router
from portfolio_analytics_api.application import (
    MarketDataNotFoundError,
    MarketDataProvider,
    PortfolioAlreadyExistsError,
    PortfolioAnalyticsService,
    PortfolioAnalyticsUnavailableError,
    PortfolioNotFoundError,
    PortfolioRepository,
    PortfolioService,
)
from portfolio_analytics_api.domain import AnalyticsMethodology, InvalidPriceSeriesError


def create_app(
    portfolio_repository: PortfolioRepository,
    market_data_provider: MarketDataProvider,
    methodology: AnalyticsMethodology,
) -> FastAPI:
    app = FastAPI(title="Portfolio Analytics API")
    portfolio_service = PortfolioService(portfolio_repository)
    analytics_service = PortfolioAnalyticsService(
        repository=portfolio_repository,
        market_data_provider=market_data_provider,
        methodology=methodology,
    )
    app.include_router(build_portfolio_router(portfolio_service, analytics_service))

    @app.exception_handler(PortfolioNotFoundError)
    async def portfolio_not_found_handler(
        _request: Request, error: PortfolioNotFoundError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND, "portfolio_not_found", str(error)
        )

    @app.exception_handler(PortfolioAlreadyExistsError)
    async def portfolio_conflict_handler(
        _request: Request, error: PortfolioAlreadyExistsError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "portfolio_conflict",
            str(error),
        )

    @app.exception_handler(MarketDataNotFoundError)
    async def market_data_not_found_handler(
        _request: Request, error: MarketDataNotFoundError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "market_data_not_found",
            str(error),
        )

    @app.exception_handler(PortfolioAnalyticsUnavailableError)
    async def analytics_unavailable_handler(
        _request: Request, error: PortfolioAnalyticsUnavailableError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "analytics_unavailable",
            str(error),
        )

    @app.exception_handler(InvalidPriceSeriesError)
    async def invalid_prices_handler(
        _request: Request, error: InvalidPriceSeriesError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_price_series",
            str(error),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "request validation failed",
        )

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )
