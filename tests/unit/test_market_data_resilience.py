import asyncio
from datetime import date
from decimal import Decimal

import pytest

from portfolio_analytics_api.application import (
    MarketDataInvalidResponseError,
    MarketDataNotFoundError,
    MarketDataRateLimitError,
    MarketDataResult,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
)
from portfolio_analytics_api.domain import PriceBar
from portfolio_analytics_api.infrastructure import RetryingMarketDataProvider


class ScriptedProvider:
    def __init__(self, outcomes: list[MarketDataResult | Exception]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> MarketDataResult:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def market_data_result() -> MarketDataResult:
    return MarketDataResult((PriceBar("AAPL", date(2026, 1, 2), Decimal("100")),))


@pytest.mark.anyio
async def test_retryable_errors_use_bounded_exponential_backoff() -> None:
    upstream = ScriptedProvider(
        [
            MarketDataUnavailableError(),
            MarketDataTimeoutError(),
            market_data_result(),
        ]
    )
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    provider = RetryingMarketDataProvider(
        upstream,
        max_attempts=3,
        initial_backoff_seconds=0.25,
        operation_timeout_seconds=1,
        sleeper=record_sleep,
    )

    result = await provider.get_price_bars("AAPL", date(2026, 1, 1), date(2026, 1, 31))

    assert result == market_data_result()
    assert upstream.calls == 3
    assert delays == [0.25, 0.5]


@pytest.mark.anyio
async def test_retry_exhaustion_preserves_stable_error() -> None:
    upstream = ScriptedProvider([MarketDataRateLimitError()] * 3)
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    provider = RetryingMarketDataProvider(
        upstream,
        sleeper=record_sleep,
    )

    with pytest.raises(MarketDataRateLimitError):
        await provider.get_price_bars("AAPL", date(2026, 1, 1), date(2026, 1, 31))

    assert upstream.calls == 3
    assert delays == [0.25, 0.5]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [
        MarketDataNotFoundError("INVALID"),
        MarketDataInvalidResponseError("bad payload"),
    ],
)
async def test_deterministic_errors_are_not_retried(error: Exception) -> None:
    upstream = ScriptedProvider([error])
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    provider = RetryingMarketDataProvider(upstream, sleeper=record_sleep)

    with pytest.raises(type(error)):
        await provider.get_price_bars("INVALID", date(2026, 1, 1), date(2026, 1, 31))

    assert upstream.calls == 1
    assert delays == []


@pytest.mark.anyio
async def test_operation_deadline_prevents_infinite_wait() -> None:
    class NeverReturnsProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def get_price_bars(
            self,
            symbol: str,
            start_date: date,
            end_date: date,
        ) -> MarketDataResult:
            self.calls += 1
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    upstream = NeverReturnsProvider()
    provider = RetryingMarketDataProvider(
        upstream,
        operation_timeout_seconds=0.01,
    )

    with pytest.raises(MarketDataTimeoutError):
        await provider.get_price_bars("AAPL", date(2026, 1, 1), date(2026, 1, 31))

    assert upstream.calls == 1


def test_retry_configuration_is_validated() -> None:
    upstream = ScriptedProvider([market_data_result()])

    with pytest.raises(ValueError, match="max_attempts"):
        RetryingMarketDataProvider(upstream, max_attempts=0)
    with pytest.raises(ValueError, match="backoff"):
        RetryingMarketDataProvider(upstream, initial_backoff_seconds=-1)
    with pytest.raises(ValueError, match="timeout"):
        RetryingMarketDataProvider(upstream, operation_timeout_seconds=0)
