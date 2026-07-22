import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from redis.exceptions import ConnectionError

from portfolio_analytics_api.application import (
    MarketDataNotFoundError,
    MarketDataResult,
    MarketDataUnavailableError,
)
from portfolio_analytics_api.domain import PriceBar
from portfolio_analytics_api.infrastructure import CachedMarketDataProvider


@dataclass
class MutableClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class CountingProvider:
    def __init__(self, bars: tuple[PriceBar, ...]) -> None:
        self.bars = bars
        self.calls = 0
        self.error: Exception | None = None

    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> MarketDataResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return MarketDataResult(
            tuple(
                bar
                for bar in self.bars
                if bar.symbol == symbol and start_date <= bar.date <= end_date
            )
        )


class FakeCacheStore:
    def __init__(self, clock: MutableClock) -> None:
        self.clock = clock
        self.values: dict[str, tuple[str, datetime]] = {}
        self.set_ttls: dict[str, int] = {}
        self.fail_reads = False
        self.fail_writes = False

    async def get(self, name: str) -> str | bytes | None:
        if self.fail_reads:
            raise ConnectionError("redis unavailable")
        cached = self.values.get(name)
        if cached is None:
            return None
        value, expires_at = cached
        if expires_at <= self.clock():
            self.values.pop(name)
            return None
        return value

    async def set(
        self,
        name: str,
        value: str,
        ex: int | timedelta | None = None,
    ) -> object:
        if self.fail_writes:
            raise ConnectionError("redis unavailable")
        if not isinstance(ex, int):
            raise ValueError("fake cache requires an integer TTL")
        self.values[name] = (value, self.clock() + timedelta(seconds=ex))
        self.set_ttls[name] = ex
        return True


@pytest.fixture
def price_bars() -> tuple[PriceBar, ...]:
    return (
        PriceBar("AAPL", date(2026, 1, 2), Decimal("100.12500000")),
        PriceBar("AAPL", date(2026, 1, 5), Decimal("101.25000000")),
    )


def build_provider(
    upstream: CountingProvider,
    cache: FakeCacheStore,
    clock: MutableClock,
    *,
    mutable_ttl: int = 300,
    historical_ttl: int = 86400,
) -> CachedMarketDataProvider:
    return CachedMarketDataProvider(
        upstream,
        cache,
        provider_name="YFINANCE",
        mutable_ttl_seconds=mutable_ttl,
        historical_ttl_seconds=historical_ttl,
        stale_ttl_seconds=604800,
        clock=clock,
    )


@pytest.mark.anyio
async def test_cache_hit_avoids_provider_and_round_trips_decimal(
    price_bars: tuple[PriceBar, ...],
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = MutableClock(datetime(2026, 1, 5, 12, tzinfo=UTC))
    upstream = CountingProvider(price_bars)
    cache = FakeCacheStore(clock)
    provider = build_provider(upstream, cache, clock)

    with caplog.at_level(logging.INFO):
        first = await provider.get_price_bars(
            " aapl ", date(2026, 1, 2), date(2026, 1, 5)
        )
        second = await provider.get_price_bars(
            "AAPL", date(2026, 1, 2), date(2026, 1, 5)
        )

    assert first.price_bars == price_bars
    assert second.price_bars == price_bars
    assert upstream.calls == 1
    assert second.price_bars[0].adjusted_close == Decimal("100.12500000")
    assert first.stale is second.stale is False
    assert {getattr(record, "cache_status", None) for record in caplog.records} >= {
        "miss",
        "hit",
    }
    assert len(cache.values) == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("end_date", "expected_ttl"),
    [
        (date(2026, 1, 5), 300),
        (date(2026, 1, 4), 86400),
    ],
)
async def test_cache_selects_ttl_by_data_mutability(
    price_bars: tuple[PriceBar, ...],
    end_date: date,
    expected_ttl: int,
) -> None:
    clock = MutableClock(datetime(2026, 1, 5, 12, tzinfo=UTC))
    upstream = CountingProvider(price_bars)
    cache = FakeCacheStore(clock)
    provider = build_provider(upstream, cache, clock)

    await provider.get_price_bars("AAPL", date(2026, 1, 2), end_date)

    fresh_ttls = [
        ttl for key, ttl in cache.set_ttls.items() if not key.endswith(":stale")
    ]
    stale_ttls = [ttl for key, ttl in cache.set_ttls.items() if key.endswith(":stale")]
    assert fresh_ttls == [expected_ttl]
    assert stale_ttls == [604800]


@pytest.mark.anyio
async def test_expired_cache_fetches_provider_again(
    price_bars: tuple[PriceBar, ...],
) -> None:
    clock = MutableClock(datetime(2026, 1, 5, 12, tzinfo=UTC))
    upstream = CountingProvider(price_bars)
    cache = FakeCacheStore(clock)
    provider = build_provider(upstream, cache, clock, mutable_ttl=1)

    await provider.get_price_bars("AAPL", date(2026, 1, 2), date(2026, 1, 5))
    clock.advance(2)
    await provider.get_price_bars("AAPL", date(2026, 1, 2), date(2026, 1, 5))

    assert upstream.calls == 2


@pytest.mark.anyio
async def test_transient_failure_returns_valid_stale_copy(
    price_bars: tuple[PriceBar, ...],
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = MutableClock(datetime(2026, 1, 5, 12, tzinfo=UTC))
    upstream = CountingProvider(price_bars)
    cache = FakeCacheStore(clock)
    provider = build_provider(upstream, cache, clock, mutable_ttl=1)

    await provider.get_price_bars("AAPL", date(2026, 1, 2), date(2026, 1, 5))
    clock.advance(2)
    upstream.error = MarketDataUnavailableError()
    with caplog.at_level(logging.INFO):
        result = await provider.get_price_bars(
            "AAPL", date(2026, 1, 2), date(2026, 1, 5)
        )

    assert result.price_bars == price_bars
    assert result.stale is True
    assert upstream.calls == 2
    assert any(
        getattr(record, "cache_status", None) == "stale" for record in caplog.records
    )


@pytest.mark.anyio
async def test_deterministic_failure_never_returns_stale_copy(
    price_bars: tuple[PriceBar, ...],
) -> None:
    clock = MutableClock(datetime(2026, 1, 5, 12, tzinfo=UTC))
    upstream = CountingProvider(price_bars)
    cache = FakeCacheStore(clock)
    provider = build_provider(upstream, cache, clock, mutable_ttl=1)

    await provider.get_price_bars("AAPL", date(2026, 1, 2), date(2026, 1, 5))
    clock.advance(2)
    upstream.error = MarketDataNotFoundError("AAPL")

    with pytest.raises(MarketDataNotFoundError):
        await provider.get_price_bars("AAPL", date(2026, 1, 2), date(2026, 1, 5))


@pytest.mark.anyio
async def test_corrupt_stale_copy_is_never_returned(
    price_bars: tuple[PriceBar, ...],
) -> None:
    clock = MutableClock(datetime(2026, 1, 5, 12, tzinfo=UTC))
    upstream = CountingProvider(price_bars)
    cache = FakeCacheStore(clock)
    provider = build_provider(upstream, cache, clock, mutable_ttl=1)
    key = "market-data:v1:yfinance:1d:adjusted-close:AAPL:2026-01-02:2026-01-05"

    await provider.get_price_bars("AAPL", date(2026, 1, 2), date(2026, 1, 5))
    clock.advance(2)
    cache.values[f"{key}:stale"] = ("not-json", clock() + timedelta(minutes=5))
    upstream.error = MarketDataUnavailableError()

    with pytest.raises(MarketDataUnavailableError):
        await provider.get_price_bars("AAPL", date(2026, 1, 2), date(2026, 1, 5))


@pytest.mark.anyio
async def test_corrupt_cache_is_ignored_and_replaced(
    price_bars: tuple[PriceBar, ...],
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = MutableClock(datetime(2026, 1, 5, 12, tzinfo=UTC))
    upstream = CountingProvider(price_bars)
    cache = FakeCacheStore(clock)
    key = "market-data:v1:yfinance:1d:adjusted-close:AAPL:2026-01-02:2026-01-05"
    cache.values[key] = ("not-json", clock() + timedelta(minutes=5))
    provider = build_provider(upstream, cache, clock)

    with caplog.at_level(logging.INFO):
        result = await provider.get_price_bars(
            "AAPL", date(2026, 1, 2), date(2026, 1, 5)
        )

    assert result.price_bars == price_bars
    assert result.stale is False
    assert upstream.calls == 1
    assert cache.values[key][0] != "not-json"
    assert any(
        getattr(record, "cache_status", None) == "corrupt" for record in caplog.records
    )


@pytest.mark.anyio
@pytest.mark.parametrize("failure_mode", ["read", "write"])
async def test_redis_failure_safely_bypasses_cache(
    price_bars: tuple[PriceBar, ...],
    caplog: pytest.LogCaptureFixture,
    failure_mode: str,
) -> None:
    clock = MutableClock(datetime(2026, 1, 5, 12, tzinfo=UTC))
    upstream = CountingProvider(price_bars)
    cache = FakeCacheStore(clock)
    cache.fail_reads = failure_mode == "read"
    cache.fail_writes = failure_mode == "write"
    provider = build_provider(upstream, cache, clock)

    with caplog.at_level(logging.INFO):
        result = await provider.get_price_bars(
            "AAPL", date(2026, 1, 2), date(2026, 1, 5)
        )

    assert result.price_bars == price_bars
    assert result.stale is False
    assert upstream.calls == 1
    assert any(
        getattr(record, "cache_status", None) == "bypass" for record in caplog.records
    )


def test_cache_configuration_is_validated(
    price_bars: tuple[PriceBar, ...],
) -> None:
    clock = MutableClock(datetime(2026, 1, 5, 12, tzinfo=UTC))
    upstream = CountingProvider(price_bars)
    cache = FakeCacheStore(clock)

    with pytest.raises(ValueError, match="TTL"):
        CachedMarketDataProvider(
            upstream,
            cache,
            provider_name="yfinance",
            mutable_ttl_seconds=0,
        )
    with pytest.raises(ValueError, match="namespace"):
        CachedMarketDataProvider(
            upstream,
            cache,
            provider_name=" ",
        )
