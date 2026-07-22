import hashlib
import logging
from collections.abc import Awaitable
from datetime import timedelta
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from redis.exceptions import RedisError

from portfolio_analytics_api.application import InsightGenerator
from portfolio_analytics_api.domain import GeneratedInsight, InsightInput
from portfolio_analytics_api.infrastructure.insights.serialization import (
    serialize_insight_input,
)

logger = logging.getLogger(__name__)


class AsyncInsightCacheStore(Protocol):
    def get(self, name: str) -> Awaitable[str | bytes | None]: ...

    def set(
        self,
        name: str,
        value: str,
        ex: int | timedelta | None = None,
    ) -> Awaitable[object]: ...


class _CachedInsight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1, le=1)
    summary: str = Field(min_length=1, max_length=1200)
    additional_limitations: list[str] = Field(default_factory=list, max_length=3)


class CachedInsightGenerator:
    def __init__(
        self,
        generator: InsightGenerator,
        cache: AsyncInsightCacheStore,
        ttl_seconds: int = 86400,
        namespace: str = "portfolio-insight",
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("insight cache TTL must be positive")
        if not namespace.strip():
            raise ValueError("insight cache namespace must not be empty")
        self._generator = generator
        self._cache = cache
        self._ttl_seconds = ttl_seconds
        self._namespace = namespace.strip().lower()

    @property
    def generator_name(self) -> str:
        return self._generator.generator_name

    @property
    def model_name(self) -> str:
        return self._generator.model_name

    @property
    def prompt_version(self) -> str:
        return self._generator.prompt_version

    async def generate(self, insight_input: InsightInput) -> GeneratedInsight:
        key = self._key(insight_input)
        cache_available = True
        try:
            cached = await self._cache.get(key)
        except RedisError:
            cache_available = False
            cached = None
            self._log("bypass", key)

        if cached is not None:
            try:
                parsed = _CachedInsight.model_validate_json(cached)
            except (ValidationError, UnicodeDecodeError):
                self._log("corrupt", key)
            else:
                self._log("hit", key)
                return GeneratedInsight(
                    summary=parsed.summary,
                    additional_limitations=tuple(parsed.additional_limitations),
                )
        elif cache_available:
            self._log("miss", key)

        generated = await self._generator.generate(insight_input)
        if not cache_available:
            return generated
        payload = _CachedInsight(
            schema_version=1,
            summary=generated.summary,
            additional_limitations=list(generated.additional_limitations),
        ).model_dump_json()
        try:
            await self._cache.set(key, payload, ex=self._ttl_seconds)
        except RedisError:
            self._log("bypass", key)
        return generated

    def _key(self, insight_input: InsightInput) -> str:
        digest = hashlib.sha256(
            serialize_insight_input(insight_input).encode("utf-8")
        ).hexdigest()
        identity = ":".join((self.generator_name, self.model_name, self.prompt_version))
        return f"{self._namespace}:v1:{identity}:{digest}"

    @staticmethod
    def _log(cache_status: str, key: str) -> None:
        logger.info(
            "insight cache %s",
            cache_status,
            extra={"cache_status": cache_status, "cache_key": key},
        )
