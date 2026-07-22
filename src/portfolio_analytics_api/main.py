from datetime import date
from decimal import Decimal

import redis.asyncio as redis

from portfolio_analytics_api.api import create_app
from portfolio_analytics_api.application import InsightGenerator, UnitOfWork
from portfolio_analytics_api.core import get_settings
from portfolio_analytics_api.domain import AnalyticsMethodology
from portfolio_analytics_api.infrastructure import (
    Argon2PasswordHasher,
    CachedInsightGenerator,
    CachedMarketDataProvider,
    DeepSeekInsightGenerator,
    JwtAccessTokenService,
    RetryingMarketDataProvider,
    YFinanceMarketDataProvider,
)
from portfolio_analytics_api.infrastructure.database import (
    SqlAlchemyUnitOfWork,
    create_database_engine,
    create_session_factory,
)

_settings = get_settings()
if _settings.jwt_secret_key is None:
    raise RuntimeError("JWT_SECRET_KEY must be configured")
_engine = create_database_engine(_settings.database_url)
_session_factory = create_session_factory(_engine)
_redis = redis.Redis.from_url(
    _settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=_settings.redis_connect_timeout_seconds,
    socket_timeout=_settings.redis_read_timeout_seconds,
)
_deepseek_api_key = (
    _settings.deepseek_api_key.get_secret_value()
    if _settings.deepseek_api_key is not None
    else ""
)
_deepseek_generator = (
    DeepSeekInsightGenerator(
        api_key=_deepseek_api_key,
        model_name=_settings.deepseek_model,
        timeout_seconds=_settings.deepseek_timeout_seconds,
    )
    if _deepseek_api_key
    else None
)
_insight_generator: InsightGenerator | None = (
    CachedInsightGenerator(
        generator=_deepseek_generator,
        cache=_redis,
        ttl_seconds=_settings.insight_cache_ttl_seconds,
    )
    if _deepseek_generator is not None
    else None
)


def _unit_of_work_factory() -> UnitOfWork:
    return SqlAlchemyUnitOfWork(_session_factory)


async def _shutdown_resources() -> None:
    if _deepseek_generator is not None:
        await _deepseek_generator.aclose()
    await _redis.aclose()
    await _engine.dispose()


app = create_app(
    unit_of_work_factory=_unit_of_work_factory,
    market_data_provider=CachedMarketDataProvider(
        provider=RetryingMarketDataProvider(
            YFinanceMarketDataProvider(
                request_timeout_seconds=_settings.market_data_request_timeout_seconds
            ),
            max_attempts=_settings.market_data_max_attempts,
            initial_backoff_seconds=_settings.market_data_retry_backoff_seconds,
            operation_timeout_seconds=_settings.market_data_operation_timeout_seconds,
        ),
        cache=_redis,
        provider_name="yfinance",
        mutable_ttl_seconds=_settings.market_data_mutable_ttl_seconds,
        historical_ttl_seconds=_settings.market_data_historical_ttl_seconds,
        stale_ttl_seconds=_settings.market_data_stale_ttl_seconds,
    ),
    methodology=AnalyticsMethodology(
        annual_risk_free_rate=Decimal("0.04"),
        risk_free_rate_as_of=date(2026, 1, 1),
        risk_free_rate_assumption=(
            "Illustrative W1.4 fixture rate held constant over the analysis period."
        ),
    ),
    password_hasher=Argon2PasswordHasher(),
    access_token_service=JwtAccessTokenService(
        secret_key=_settings.jwt_secret_key.get_secret_value(),
        expire_minutes=_settings.access_token_expire_minutes,
    ),
    insight_generator=_insight_generator,
    shutdown_callback=_shutdown_resources,
)
