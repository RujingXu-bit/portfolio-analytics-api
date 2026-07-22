import asyncio
from uuid import uuid4

import pytest
import redis.asyncio as redis

from portfolio_analytics_api.application import (
    RateLimitExceededError,
    RateLimitRule,
)
from portfolio_analytics_api.core import Settings
from portfolio_analytics_api.infrastructure import RedisFixedWindowRateLimiter


@pytest.mark.anyio
async def test_real_redis_fixed_window_is_atomic_and_expires() -> None:
    settings = Settings()
    client = redis.Redis.from_url(
        settings.test_redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    namespace = f"test-rate-limit-{uuid4().hex}"
    limiter = RedisFixedWindowRateLimiter(
        client,
        "integration-rate-limit-hash-secret-key",
        namespace=namespace,
    )
    rule = RateLimitRule("concurrent_user", 20, 2)

    try:
        results = await asyncio.gather(
            *(limiter.enforce(rule, "user:private-id") for _ in range(30)),
            return_exceptions=True,
        )
        allowed = sum(result is None for result in results)
        blocked = [
            result for result in results if isinstance(result, RateLimitExceededError)
        ]
        keys = [key async for key in client.scan_iter(match=f"{namespace}:*")]

        assert allowed == 20
        assert len(blocked) == 10
        assert all(1 <= error.retry_after_seconds <= 2 for error in blocked)
        assert len(keys) == 1
        assert "private-id" not in keys[0]
        ttl = await client.ttl(keys[0])
        assert 0 < ttl <= 2
        await asyncio.sleep(2.1)
        assert await client.exists(keys[0]) == 0
    finally:
        keys = [key async for key in client.scan_iter(match=f"{namespace}:*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()
