import hashlib
import hmac
import logging
import math
from collections.abc import Awaitable, Callable
from time import time
from typing import Protocol

from portfolio_analytics_api.application import (
    RateLimitExceededError,
    RateLimitRule,
)

logger = logging.getLogger(__name__)

_FIXED_WINDOW_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


class RedisScriptClient(Protocol):
    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str | int,
    ) -> Awaitable[object]: ...


class RedisFixedWindowRateLimiter:
    def __init__(
        self,
        cache: RedisScriptClient,
        hash_key: str,
        *,
        namespace: str = "rate-limit",
        clock: Callable[[], float] = time,
    ) -> None:
        if not hash_key:
            raise ValueError("rate-limit hash key must not be empty")
        if not namespace:
            raise ValueError("rate-limit namespace must not be empty")
        self._cache = cache
        self._hash_key = hash_key.encode("utf-8")
        self._namespace = namespace
        self._clock = clock

    async def enforce(self, rule: RateLimitRule, identifier: str) -> None:
        now = self._clock()
        bucket = math.floor(now / rule.window_seconds)
        window_end = (bucket + 1) * rule.window_seconds
        expires_in = max(1, math.ceil(window_end - now))
        digest = hmac.new(
            self._hash_key,
            identifier.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        key = f"{self._namespace}:v1:{rule.scope}:{bucket}:{digest}"
        try:
            result = await self._cache.eval(
                _FIXED_WINDOW_SCRIPT,
                1,
                key,
                expires_in,
            )
            count, ttl = _parse_rate_limit_result(result)
        except Exception as error:
            logger.warning(
                "rate_limit_bypass",
                extra={
                    "event": "rate_limit_bypass",
                    "error_type": type(error).__name__,
                },
            )
            return

        if count > rule.limit:
            raise RateLimitExceededError(max(1, ttl))


def _parse_rate_limit_result(result: object) -> tuple[int, int]:
    if not isinstance(result, (list, tuple)) or len(result) != 2:
        raise ValueError("invalid rate-limit response")
    count, ttl = result
    if not isinstance(count, int) or not isinstance(ttl, int):
        raise ValueError("invalid rate-limit response")
    return count, ttl
