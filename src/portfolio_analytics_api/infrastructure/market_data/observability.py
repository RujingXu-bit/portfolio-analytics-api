import logging
from collections.abc import Callable
from datetime import date
from time import perf_counter

from portfolio_analytics_api.application import (
    MarketDataInvalidResponseError,
    MarketDataNotFoundError,
    MarketDataProvider,
    MarketDataRateLimitError,
    MarketDataResult,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
)

logger = logging.getLogger(__name__)


class ObservedMarketDataProvider:
    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        provider_name: str,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        normalized_name = provider_name.strip().lower()
        if not normalized_name:
            raise ValueError("provider name must not be empty")
        self._provider = provider
        self._provider_name = normalized_name
        self._clock = clock

    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> MarketDataResult:
        started_at = self._clock()
        try:
            result = await self._provider.get_price_bars(
                symbol,
                start_date,
                end_date,
            )
        except Exception as error:
            logger.warning(
                "market data provider request failed",
                extra={
                    "event": "market_data.provider.request",
                    "provider": self._provider_name,
                    "symbol": symbol,
                    "duration_ms": round((self._clock() - started_at) * 1000, 3),
                    "outcome": "error",
                    "error_category": _error_category(error),
                    "error_type": type(error).__name__,
                },
            )
            raise

        logger.info(
            "market data provider request completed",
            extra={
                "event": "market_data.provider.request",
                "provider": self._provider_name,
                "symbol": symbol,
                "duration_ms": round((self._clock() - started_at) * 1000, 3),
                "outcome": "success",
            },
        )
        return result


def _error_category(error: Exception) -> str:
    if isinstance(error, MarketDataRateLimitError):
        return "rate_limited"
    if isinstance(error, MarketDataTimeoutError):
        return "timeout"
    if isinstance(error, MarketDataUnavailableError):
        return "unavailable"
    if isinstance(error, MarketDataNotFoundError):
        return "not_found"
    if isinstance(error, MarketDataInvalidResponseError):
        return "invalid_response"
    if isinstance(error, ValueError):
        return "invalid_request"
    return "unexpected"
