from datetime import date
from decimal import Decimal

import redis.asyncio as redis

from portfolio_analytics_api.api import create_app
from portfolio_analytics_api.application import UnitOfWork
from portfolio_analytics_api.core import get_settings
from portfolio_analytics_api.domain import AnalyticsMethodology
from portfolio_analytics_api.infrastructure import (
    CachedMarketDataProvider,
    RetryingMarketDataProvider,
    YFinanceMarketDataProvider,
)
from portfolio_analytics_api.infrastructure.database import (
    SqlAlchemyUnitOfWork,
    create_database_engine,
    create_session_factory,
)

_settings = get_settings()
_engine = create_database_engine(_settings.database_url)
_session_factory = create_session_factory(_engine)
_redis = redis.Redis.from_url(
    _settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=_settings.redis_connect_timeout_seconds,
    socket_timeout=_settings.redis_read_timeout_seconds,
)


def _unit_of_work_factory() -> UnitOfWork:
    return SqlAlchemyUnitOfWork(_session_factory)


async def _shutdown_resources() -> None:
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
    shutdown_callback=_shutdown_resources,
)
