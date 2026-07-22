import asyncio
import os
from datetime import date
from decimal import Decimal

import redis.asyncio as redis
from sqlalchemy.engine import make_url

from benchmarks.fixture import BENCHMARK_SYMBOL, PRICE_BARS
from portfolio_analytics_api.api import create_app
from portfolio_analytics_api.application import (
    MarketDataNotFoundError,
    MarketDataResult,
    UnitOfWork,
)
from portfolio_analytics_api.core import Settings, configure_logging
from portfolio_analytics_api.domain import AnalyticsMethodology
from portfolio_analytics_api.infrastructure import (
    Argon2PasswordHasher,
    CachedMarketDataProvider,
    JwtAccessTokenService,
    ObservedMarketDataProvider,
    RetryingMarketDataProvider,
)
from portfolio_analytics_api.infrastructure.database import (
    SqlAlchemyUnitOfWork,
    create_database_engine,
    create_session_factory,
)

_BENCHMARK_JWT_SECRET = "benchmark-only-jwt-secret-key-32-characters"
_PROVIDER_DELAY_SECONDS = 0.05
_settings = Settings()
_database_name = make_url(_settings.test_database_url).database or ""
if not _database_name.endswith("_test"):
    raise RuntimeError("benchmark database name must end with _test")
_cache_namespace = os.environ.get("BENCHMARK_CACHE_NAMESPACE", "").strip()
if not _cache_namespace.startswith("benchmark-"):
    raise RuntimeError("BENCHMARK_CACHE_NAMESPACE must start with 'benchmark-'")

configure_logging("INFO")
_engine = create_database_engine(_settings.test_database_url)
_session_factory = create_session_factory(_engine)
_redis = redis.Redis.from_url(
    _settings.test_redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)


class DelayedFixtureMarketDataProvider:
    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> MarketDataResult:
        await asyncio.sleep(_PROVIDER_DELAY_SECONDS)
        if symbol.strip().upper() != BENCHMARK_SYMBOL:
            raise MarketDataNotFoundError(symbol)
        bars = tuple(bar for bar in PRICE_BARS if start_date <= bar.date <= end_date)
        if not bars:
            raise MarketDataNotFoundError(symbol)
        return MarketDataResult(bars)


def _unit_of_work_factory() -> UnitOfWork:
    return SqlAlchemyUnitOfWork(_session_factory)


async def _shutdown_resources() -> None:
    await _redis.aclose()
    await _engine.dispose()


app = create_app(
    unit_of_work_factory=_unit_of_work_factory,
    market_data_provider=CachedMarketDataProvider(
        RetryingMarketDataProvider(
            ObservedMarketDataProvider(
                DelayedFixtureMarketDataProvider(),
                provider_name="delayed-fixture",
            ),
            max_attempts=1,
            operation_timeout_seconds=2,
        ),
        _redis,
        provider_name="delayed-fixture",
        mutable_ttl_seconds=600,
        historical_ttl_seconds=600,
        stale_ttl_seconds=600,
        namespace=_cache_namespace,
    ),
    methodology=AnalyticsMethodology(
        annual_risk_free_rate=Decimal("0.04"),
        risk_free_rate_as_of=date(2026, 1, 1),
        risk_free_rate_assumption="Fixed synthetic benchmark rate.",
    ),
    password_hasher=Argon2PasswordHasher(),
    access_token_service=JwtAccessTokenService(_BENCHMARK_JWT_SECRET, 30),
    shutdown_callback=_shutdown_resources,
)
