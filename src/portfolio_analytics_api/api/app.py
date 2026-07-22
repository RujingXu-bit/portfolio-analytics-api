from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from portfolio_analytics_api.api.routes import build_portfolio_router
from portfolio_analytics_api.application import (
    MarketDataInvalidResponseError,
    MarketDataNotFoundError,
    MarketDataProvider,
    MarketDataRateLimitError,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
    PortfolioAlreadyExistsError,
    PortfolioAnalyticsService,
    PortfolioAnalyticsUnavailableError,
    PortfolioNotFoundError,
    PortfolioService,
    TransactionIdempotencyConflictError,
    TransactionService,
    UnitOfWorkFactory,
)
from portfolio_analytics_api.domain import (
    AnalyticsMethodology,
    InvalidPriceSeriesError,
    InvalidTransactionError,
)


def create_app(
    unit_of_work_factory: UnitOfWorkFactory,
    market_data_provider: MarketDataProvider,
    methodology: AnalyticsMethodology,
    shutdown_callback: Callable[[], Awaitable[None]] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if shutdown_callback is not None:
            await shutdown_callback()

    app = FastAPI(title="Portfolio Analytics API", lifespan=lifespan)
    portfolio_service = PortfolioService(unit_of_work_factory)
    transaction_service = TransactionService(unit_of_work_factory)
    analytics_service = PortfolioAnalyticsService(
        unit_of_work_factory=unit_of_work_factory,
        market_data_provider=market_data_provider,
        methodology=methodology,
    )
    app.include_router(
        build_portfolio_router(
            portfolio_service,
            transaction_service,
            analytics_service,
        )
    )

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

    @app.exception_handler(MarketDataInvalidResponseError)
    async def market_data_invalid_response_handler(
        _request: Request, error: MarketDataInvalidResponseError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "market_data_invalid_response",
            str(error),
        )

    @app.exception_handler(MarketDataRateLimitError)
    async def market_data_rate_limit_handler(
        _request: Request, error: MarketDataRateLimitError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "market_data_rate_limited",
            str(error),
        )

    @app.exception_handler(MarketDataUnavailableError)
    async def market_data_unavailable_handler(
        _request: Request, error: MarketDataUnavailableError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "market_data_unavailable",
            str(error),
        )

    @app.exception_handler(MarketDataTimeoutError)
    async def market_data_timeout_handler(
        _request: Request, error: MarketDataTimeoutError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "market_data_timeout",
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

    @app.exception_handler(TransactionIdempotencyConflictError)
    async def transaction_idempotency_conflict_handler(
        _request: Request, error: TransactionIdempotencyConflictError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "transaction_idempotency_conflict",
            str(error),
        )

    @app.exception_handler(InvalidTransactionError)
    async def invalid_transaction_handler(
        _request: Request, error: InvalidTransactionError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_transaction",
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
