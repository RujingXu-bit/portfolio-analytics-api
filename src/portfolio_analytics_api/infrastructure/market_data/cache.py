import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol

from redis.exceptions import RedisError

from portfolio_analytics_api.application import (
    MarketDataProvider,
    MarketDataResult,
    MarketDataRetryableError,
)
from portfolio_analytics_api.domain import PriceBar

logger = logging.getLogger(__name__)


class AsyncCacheStore(Protocol):
    def get(self, name: str) -> Awaitable[str | bytes | None]: ...

    def set(
        self,
        name: str,
        value: str,
        ex: int | timedelta | None = None,
    ) -> Awaitable[object]: ...


class CachedMarketDataProvider:
    def __init__(
        self,
        provider: MarketDataProvider,
        cache: AsyncCacheStore,
        *,
        provider_name: str,
        mutable_ttl_seconds: int = 300,
        historical_ttl_seconds: int = 86400,
        stale_ttl_seconds: int = 604800,
        namespace: str = "market-data",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if any(
            ttl <= 0
            for ttl in (
                mutable_ttl_seconds,
                historical_ttl_seconds,
                stale_ttl_seconds,
            )
        ):
            raise ValueError("cache TTL values must be positive")
        normalized_provider_name = provider_name.strip().lower()
        normalized_namespace = namespace.strip().lower()
        if not normalized_provider_name or not normalized_namespace:
            raise ValueError("cache provider name and namespace must not be empty")
        self._provider = provider
        self._cache = cache
        self._provider_name = normalized_provider_name
        self._mutable_ttl_seconds = mutable_ttl_seconds
        self._historical_ttl_seconds = historical_ttl_seconds
        self._stale_ttl_seconds = stale_ttl_seconds
        self._namespace = normalized_namespace
        self._clock = clock

    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> MarketDataResult:
        normalized_symbol = symbol.strip().upper()
        key = self._key(normalized_symbol, start_date, end_date)
        cache_available = True
        try:
            cached = await self._cache.get(key)
        except RedisError:
            cache_available = False
            cached = None
            self._log("bypass")

        if cached is not None:
            try:
                bars = _deserialize_price_bars(
                    cached,
                    symbol=normalized_symbol,
                    start_date=start_date,
                    end_date=end_date,
                )
            except ValueError:
                self._log("corrupt")
            else:
                self._log("hit")
                return MarketDataResult(bars)
        elif cache_available:
            self._log("miss")

        try:
            result = await self._provider.get_price_bars(
                normalized_symbol,
                start_date,
                end_date,
            )
        except MarketDataRetryableError:
            stale = await self._read_stale(
                key,
                normalized_symbol,
                start_date,
                end_date,
                cache_available=cache_available,
            )
            if stale is not None:
                return MarketDataResult(stale, stale=True)
            raise
        if not cache_available:
            return result

        payload = _serialize_price_bars(
            result.price_bars,
            symbol=normalized_symbol,
            start_date=start_date,
            end_date=end_date,
        )
        fresh_ttl = (
            self._mutable_ttl_seconds
            if end_date >= self._clock().date()
            else self._historical_ttl_seconds
        )
        try:
            await self._cache.set(key, payload, ex=fresh_ttl)
            await self._cache.set(
                self._stale_key(key),
                payload,
                ex=self._stale_ttl_seconds,
            )
        except RedisError:
            self._log("bypass")
        return result

    async def _read_stale(
        self,
        key: str,
        symbol: str,
        start_date: date,
        end_date: date,
        *,
        cache_available: bool,
    ) -> tuple[PriceBar, ...] | None:
        if not cache_available:
            return None
        try:
            raw_stale = await self._cache.get(self._stale_key(key))
        except RedisError:
            self._log("bypass")
            return None
        if raw_stale is None:
            return None
        try:
            bars = _deserialize_price_bars(
                raw_stale,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )
        except ValueError:
            self._log("corrupt")
            return None
        self._log("stale")
        return bars

    def _key(self, symbol: str, start_date: date, end_date: date) -> str:
        return (
            f"{self._namespace}:v1:{self._provider_name}:1d:adjusted-close:"
            f"{symbol}:{start_date.isoformat()}:{end_date.isoformat()}"
        )

    @staticmethod
    def _stale_key(key: str) -> str:
        return f"{key}:stale"

    @staticmethod
    def _log(cache_status: str) -> None:
        logger.info(
            "market data cache event",
            extra={
                "event": "market_data.cache",
                "cache_name": "market_data",
                "cache_status": cache_status,
            },
        )


def _serialize_price_bars(
    bars: tuple[PriceBar, ...],
    *,
    symbol: str,
    start_date: date,
    end_date: date,
) -> str:
    payload = {
        "schema_version": 1,
        "symbol": symbol,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "bars": [
            {
                "date": bar.date.isoformat(),
                "adjusted_close": str(bar.adjusted_close),
            }
            for bar in bars
        ],
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _deserialize_price_bars(
    raw_payload: str | bytes,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
) -> tuple[PriceBar, ...]:
    try:
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as error:
        raise ValueError("cache payload is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("cache payload must be an object")
    if (
        payload.get("schema_version") != 1
        or payload.get("symbol") != symbol
        or payload.get("start_date") != start_date.isoformat()
        or payload.get("end_date") != end_date.isoformat()
    ):
        raise ValueError("cache payload metadata does not match the query")
    raw_bars = payload.get("bars")
    if not isinstance(raw_bars, list) or not raw_bars:
        raise ValueError("cache payload has no price bars")

    bars: list[PriceBar] = []
    seen_dates: set[date] = set()
    for raw_bar in raw_bars:
        if not isinstance(raw_bar, dict):
            raise ValueError("cache price bar must be an object")
        try:
            session_date = date.fromisoformat(raw_bar["date"])
            adjusted_close = Decimal(raw_bar["adjusted_close"])
        except (KeyError, TypeError, ValueError, InvalidOperation) as error:
            raise ValueError("cache price bar is invalid") from error
        if (
            session_date in seen_dates
            or not start_date <= session_date <= end_date
            or not adjusted_close.is_finite()
            or adjusted_close <= 0
        ):
            raise ValueError("cache price bar violates data invariants")
        seen_dates.add(session_date)
        bars.append(PriceBar(symbol, session_date, adjusted_close))

    ordered = tuple(sorted(bars, key=lambda bar: bar.date))
    if tuple(bars) != ordered:
        raise ValueError("cache price bars are not ordered")
    return ordered
