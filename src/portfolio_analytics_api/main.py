from datetime import date
from decimal import Decimal

import redis.asyncio as redis

from portfolio_analytics_api.api import create_app
from portfolio_analytics_api.api.rate_limit import RateLimitPolicies
from portfolio_analytics_api.application import (
    InsightGenerator,
    RateLimitRule,
    UnitOfWork,
)
from portfolio_analytics_api.core import configure_logging, get_settings
from portfolio_analytics_api.domain import AnalyticsMethodology
from portfolio_analytics_api.infrastructure import (
    Argon2PasswordHasher,
    CachedInsightGenerator,
    CachedMarketDataProvider,
    DeepSeekInsightGenerator,
    JwtAccessTokenService,
    ObservedMarketDataProvider,
    RedisFixedWindowRateLimiter,
    RetryingMarketDataProvider,
    create_market_data_adapter,
)
from portfolio_analytics_api.infrastructure.database import (
    SqlAlchemyUnitOfWork,
    create_database_engine,
    create_session_factory,
)

_settings = get_settings()
configure_logging(_settings.log_level)
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
_rate_limit_hash_key = (
    _settings.rate_limit_hash_key.get_secret_value()
    if _settings.rate_limit_hash_key is not None
    else _settings.jwt_secret_key.get_secret_value()
)
_rate_limiter = (
    RedisFixedWindowRateLimiter(
        cache=_redis,
        hash_key=_rate_limit_hash_key,
        namespace=_settings.rate_limit_namespace,
    )
    if _settings.rate_limit_enabled
    else None
)
_rate_limit_policies = RateLimitPolicies(
    registration_ip=RateLimitRule(
        "registration_ip",
        _settings.rate_limit_registration_ip_limit,
        _settings.rate_limit_registration_window_seconds,
    ),
    login_ip=RateLimitRule(
        "login_ip",
        _settings.rate_limit_login_ip_limit,
        _settings.rate_limit_login_window_seconds,
    ),
    login_email=RateLimitRule(
        "login_email",
        _settings.rate_limit_login_email_limit,
        _settings.rate_limit_login_window_seconds,
    ),
    analytics_user=RateLimitRule(
        "analytics_user",
        _settings.rate_limit_analytics_user_limit,
        _settings.rate_limit_authenticated_window_seconds,
    ),
    insights_user=RateLimitRule(
        "insights_user",
        _settings.rate_limit_insights_user_limit,
        _settings.rate_limit_authenticated_window_seconds,
    ),
    authenticated_user=RateLimitRule(
        "authenticated_user",
        _settings.rate_limit_authenticated_user_limit,
        _settings.rate_limit_authenticated_window_seconds,
    ),
)
_twelve_data_api_key = (
    _settings.twelve_data_api_key.get_secret_value()
    if _settings.twelve_data_api_key is not None
    else None
)
_market_data_provider_name, _market_data_adapter = create_market_data_adapter(
    provider_name=_settings.market_data_provider,
    request_timeout_seconds=_settings.market_data_request_timeout_seconds,
    twelve_data_api_key=_twelve_data_api_key,
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
            ObservedMarketDataProvider(
                _market_data_adapter,
                provider_name=_market_data_provider_name,
            ),
            max_attempts=_settings.market_data_max_attempts,
            initial_backoff_seconds=_settings.market_data_retry_backoff_seconds,
            operation_timeout_seconds=_settings.market_data_operation_timeout_seconds,
        ),
        cache=_redis,
        provider_name=_market_data_provider_name,
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
    rate_limiter=_rate_limiter,
    rate_limit_policies=_rate_limit_policies,
    trust_proxy_headers=_settings.rate_limit_trust_proxy_headers,
    shutdown_callback=_shutdown_resources,
)
