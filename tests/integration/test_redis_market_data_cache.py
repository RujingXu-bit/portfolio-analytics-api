import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
import redis.asyncio as redis

from portfolio_analytics_api.application import MarketDataResult
from portfolio_analytics_api.core import Settings
from portfolio_analytics_api.domain import PriceBar
from portfolio_analytics_api.infrastructure import CachedMarketDataProvider


class CountingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> MarketDataResult:
        self.calls += 1
        return MarketDataResult(
            (
                PriceBar(symbol, date(2026, 1, 2), Decimal("100.12500000")),
                PriceBar(symbol, date(2026, 1, 5), Decimal("101.25000000")),
            )
        )


@pytest.mark.anyio
async def test_real_redis_cache_round_trip_ttl_and_expiry() -> None:
    settings = Settings()
    client = redis.Redis.from_url(
        settings.test_redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    namespace = f"test-market-data-{uuid4().hex}"
    upstream = CountingProvider()
    provider = CachedMarketDataProvider(
        upstream,
        client,
        provider_name="yfinance",
        mutable_ttl_seconds=1,
        historical_ttl_seconds=30,
        stale_ttl_seconds=60,
        namespace=namespace,
        clock=lambda: datetime(2026, 1, 5, 12, tzinfo=UTC),
    )
    fresh_key = f"{namespace}:v1:yfinance:1d:adjusted-close:AAPL:2026-01-02:2026-01-05"
    stale_key = f"{fresh_key}:stale"

    try:
        first = await provider.get_price_bars(
            "AAPL", date(2026, 1, 2), date(2026, 1, 5)
        )
        second = await provider.get_price_bars(
            "AAPL", date(2026, 1, 2), date(2026, 1, 5)
        )
        fresh_ttl = await client.ttl(fresh_key)
        stale_ttl = await client.ttl(stale_key)
        await asyncio.sleep(1.1)
        third = await provider.get_price_bars(
            "AAPL", date(2026, 1, 2), date(2026, 1, 5)
        )

        assert first.price_bars == second.price_bars == third.price_bars
        assert first.stale is second.stale is third.stale is False
        assert upstream.calls == 2
        assert 0 <= fresh_ttl <= 1
        assert 0 < stale_ttl <= 60
    finally:
        await client.delete(fresh_key, stale_key)
        await client.aclose()
