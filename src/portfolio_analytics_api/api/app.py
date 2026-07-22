import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from portfolio_analytics_api.api.auth_routes import build_auth_router
from portfolio_analytics_api.api.csv_import import parse_transaction_csv
from portfolio_analytics_api.api.observability import RequestObservabilityMiddleware
from portfolio_analytics_api.api.rate_limit import RateLimitPolicies
from portfolio_analytics_api.api.routes import build_portfolio_router
from portfolio_analytics_api.application import (
    AccessTokenService,
    AuthenticationError,
    AuthenticationService,
    EmailAlreadyRegisteredError,
    InsightGenerator,
    MarketDataInvalidResponseError,
    MarketDataNotFoundError,
    MarketDataProvider,
    MarketDataRateLimitError,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
    PasswordHasher,
    PortfolioAlreadyExistsError,
    PortfolioAnalyticsService,
    PortfolioAnalyticsUnavailableError,
    PortfolioInsightService,
    PortfolioNotFoundError,
    PortfolioService,
    RateLimiter,
    RateLimitExceededError,
    TransactionIdempotencyConflictError,
    TransactionImportFormatError,
    TransactionImportService,
    TransactionService,
    UnitOfWorkFactory,
)
from portfolio_analytics_api.domain import (
    AnalyticsMethodology,
    InvalidPriceSeriesError,
    InvalidTransactionError,
)

logger = logging.getLogger(__name__)


def create_app(
    unit_of_work_factory: UnitOfWorkFactory,
    market_data_provider: MarketDataProvider,
    methodology: AnalyticsMethodology,
    password_hasher: PasswordHasher,
    access_token_service: AccessTokenService,
    insight_generator: InsightGenerator | None = None,
    rate_limiter: RateLimiter | None = None,
    rate_limit_policies: RateLimitPolicies | None = None,
    trust_proxy_headers: bool = False,
    shutdown_callback: Callable[[], Awaitable[None]] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if shutdown_callback is not None:
            await shutdown_callback()

    policies = rate_limit_policies or RateLimitPolicies()
    app = FastAPI(title="Ledger Lens API", version="1.2.0", lifespan=lifespan)
    app.add_middleware(RequestObservabilityMiddleware)
    authentication_service = AuthenticationService(
        unit_of_work_factory=unit_of_work_factory,
        password_hasher=password_hasher,
        access_token_service=access_token_service,
    )
    portfolio_service = PortfolioService(unit_of_work_factory)
    transaction_service = TransactionService(unit_of_work_factory)
    transaction_import_service = TransactionImportService(
        unit_of_work_factory=unit_of_work_factory,
        transaction_service=transaction_service,
        parser=parse_transaction_csv,
    )
    analytics_service = PortfolioAnalyticsService(
        unit_of_work_factory=unit_of_work_factory,
        market_data_provider=market_data_provider,
        methodology=methodology,
    )
    insight_service = PortfolioInsightService(
        analytics_service=analytics_service,
        unit_of_work_factory=unit_of_work_factory,
        insight_generator=insight_generator,
    )
    app.include_router(
        build_portfolio_router(
            authentication_service,
            portfolio_service,
            transaction_service,
            transaction_import_service,
            analytics_service,
            insight_service,
            rate_limiter,
            policies,
        )
    )
    app.include_router(
        build_auth_router(
            authentication_service,
            rate_limiter,
            policies,
            trust_proxy_headers,
        )
    )

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        _request: Request, error: AuthenticationError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "authentication_failed",
            str(error),
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(EmailAlreadyRegisteredError)
    async def email_already_registered_handler(
        _request: Request, _error: EmailAlreadyRegisteredError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "email_already_registered",
            "email is already registered",
        )

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_handler(
        _request: Request, error: RateLimitExceededError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            str(error),
            headers={"Retry-After": str(error.retry_after_seconds)},
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

    @app.exception_handler(TransactionImportFormatError)
    async def transaction_import_format_handler(
        _request: Request, error: TransactionImportFormatError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "csv_import_invalid",
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


def _error_response(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    logger.info(
        "http error response",
        extra={
            "event": "http.error",
            "status_code": status_code,
            "error_category": code,
        },
    )
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )
