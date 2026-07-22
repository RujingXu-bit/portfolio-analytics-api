import asyncio
from collections.abc import Awaitable, Callable
from datetime import date

from portfolio_analytics_api.application import (
    MarketDataProvider,
    MarketDataResult,
    MarketDataRetryableError,
    MarketDataTimeoutError,
)

Sleeper = Callable[[float], Awaitable[None]]


class RetryingMarketDataProvider:
    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        max_attempts: int = 3,
        initial_backoff_seconds: float = 0.25,
        operation_timeout_seconds: float = 12.0,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if initial_backoff_seconds < 0:
            raise ValueError("initial_backoff_seconds must not be negative")
        if operation_timeout_seconds <= 0:
            raise ValueError("operation_timeout_seconds must be positive")
        self._provider = provider
        self._max_attempts = max_attempts
        self._initial_backoff_seconds = initial_backoff_seconds
        self._operation_timeout_seconds = operation_timeout_seconds
        self._sleeper = sleeper

    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> MarketDataResult:
        try:
            async with asyncio.timeout(self._operation_timeout_seconds):
                return await self._attempt(symbol, start_date, end_date)
        except TimeoutError as error:
            raise MarketDataTimeoutError from error

    async def _attempt(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> MarketDataResult:
        for attempt in range(1, self._max_attempts + 1):
            try:
                return await self._provider.get_price_bars(
                    symbol,
                    start_date,
                    end_date,
                )
            except MarketDataRetryableError:
                if attempt == self._max_attempts:
                    raise
                delay = self._initial_backoff_seconds * (2 ** (attempt - 1))
                await self._sleeper(delay)
        raise AssertionError("retry loop must return or raise")
