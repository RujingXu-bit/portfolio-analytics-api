from datetime import date, timedelta
from decimal import Decimal

import pytest
from redis.exceptions import ConnectionError

from portfolio_analytics_api.domain import (
    AnalyticsMethodology,
    AssetWeight,
    GeneratedInsight,
    InsightInput,
)
from portfolio_analytics_api.infrastructure import (
    CachedInsightGenerator,
    FakeInsightGenerator,
)


class FakeCacheStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.fail_reads = False
        self.fail_writes = False

    async def get(self, name: str) -> str | bytes | None:
        if self.fail_reads:
            raise ConnectionError("redis unavailable")
        return self.values.get(name)

    async def set(
        self,
        name: str,
        value: str,
        ex: int | timedelta | None = None,
    ) -> object:
        if self.fail_writes:
            raise ConnectionError("redis unavailable")
        if not isinstance(ex, int):
            raise ValueError("fake cache requires integer TTL")
        self.values[name] = value
        self.ttls[name] = ex
        return True


def insight_input() -> InsightInput:
    return InsightInput(
        as_of=date(2026, 1, 30),
        simple_return=0.05,
        annualized_volatility=0.2,
        max_drawdown=-0.1,
        sharpe_ratio=0.6,
        asset_weights=(AssetWeight("DEMO", Decimal("700"), Decimal("0.7")),),
        methodology=AnalyticsMethodology(
            annual_risk_free_rate=Decimal("0.04"),
            risk_free_rate_as_of=date(2026, 1, 1),
            risk_free_rate_assumption="Fixed cache-test rate.",
        ),
        stale=False,
    )


def generated_insight() -> GeneratedInsight:
    return GeneratedInsight(
        summary=("Historical metrics indicate elevated variability and concentration."),
        additional_limitations=("The observation window is limited.",),
    )


@pytest.mark.anyio
async def test_cache_hit_avoids_repeating_generator_call() -> None:
    upstream = FakeInsightGenerator(generated_insight())
    cache = FakeCacheStore()
    generator = CachedInsightGenerator(upstream, cache, ttl_seconds=123)

    first = await generator.generate(insight_input())
    second = await generator.generate(insight_input())

    assert first == second == generated_insight()
    assert len(upstream.inputs) == 1
    assert list(cache.ttls.values()) == [123]


@pytest.mark.anyio
async def test_corrupt_cache_is_ignored_and_replaced() -> None:
    upstream = FakeInsightGenerator(generated_insight())
    cache = FakeCacheStore()
    generator = CachedInsightGenerator(upstream, cache)
    await generator.generate(insight_input())
    key = next(iter(cache.values))
    cache.values[key] = "not-json"

    result = await generator.generate(insight_input())

    assert result == generated_insight()
    assert len(upstream.inputs) == 2
    assert cache.values[key] != "not-json"


@pytest.mark.anyio
@pytest.mark.parametrize("failure_mode", ["read", "write"])
async def test_redis_failure_safely_bypasses_insight_cache(
    failure_mode: str,
) -> None:
    upstream = FakeInsightGenerator(generated_insight())
    cache = FakeCacheStore()
    cache.fail_reads = failure_mode == "read"
    cache.fail_writes = failure_mode == "write"
    generator = CachedInsightGenerator(upstream, cache)

    result = await generator.generate(insight_input())

    assert result == generated_insight()
    assert len(upstream.inputs) == 1


def test_insight_cache_configuration_is_validated() -> None:
    upstream = FakeInsightGenerator(generated_insight())
    cache = FakeCacheStore()

    with pytest.raises(ValueError, match="TTL"):
        CachedInsightGenerator(upstream, cache, ttl_seconds=0)
    with pytest.raises(ValueError, match="namespace"):
        CachedInsightGenerator(upstream, cache, namespace=" ")
