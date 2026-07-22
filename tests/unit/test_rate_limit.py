import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal

import httpx
import pytest

from portfolio_analytics_api.api import create_app
from portfolio_analytics_api.api.rate_limit import RateLimitPolicies
from portfolio_analytics_api.application import (
    RateLimitExceededError,
    RateLimitRule,
    UnitOfWork,
)
from portfolio_analytics_api.domain import AnalyticsMethodology
from portfolio_analytics_api.infrastructure import (
    FakeMarketDataProvider,
    InMemoryStore,
    InMemoryUnitOfWork,
    JwtAccessTokenService,
    RedisFixedWindowRateLimiter,
)

_JWT_SECRET = "rate-limit-test-jwt-secret-with-32-characters"


class FastPasswordHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{password}"


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self.counts: dict[tuple[str, str], int] = defaultdict(int)
        self.calls: list[tuple[RateLimitRule, str]] = []

    async def enforce(self, rule: RateLimitRule, identifier: str) -> None:
        self.calls.append((rule, identifier))
        key = (rule.scope, identifier)
        self.counts[key] += 1
        if self.counts[key] > rule.limit:
            raise RateLimitExceededError(rule.window_seconds)


@asynccontextmanager
async def rate_limited_client(
    limiter: InMemoryRateLimiter,
    policies: RateLimitPolicies,
    *,
    trust_proxy_headers: bool = False,
) -> AsyncIterator[httpx.AsyncClient]:
    store = InMemoryStore()

    def unit_of_work_factory() -> UnitOfWork:
        return InMemoryUnitOfWork(store)

    app = create_app(
        unit_of_work_factory=unit_of_work_factory,
        market_data_provider=FakeMarketDataProvider({}),
        methodology=AnalyticsMethodology(
            annual_risk_free_rate=Decimal("0"),
            risk_free_rate_as_of=date(2026, 1, 1),
            risk_free_rate_assumption="Fixed rate-limit test rate.",
        ),
        password_hasher=FastPasswordHasher(),
        access_token_service=JwtAccessTokenService(_JWT_SECRET, 30),
        rate_limiter=limiter,
        rate_limit_policies=policies,
        trust_proxy_headers=trust_proxy_headers,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


def roomy_policies(**overrides: RateLimitRule) -> RateLimitPolicies:
    values = {
        "registration_ip": RateLimitRule("registration_ip", 100, 600),
        "login_ip": RateLimitRule("login_ip", 100, 600),
        "login_email": RateLimitRule("login_email", 100, 600),
        "analytics_user": RateLimitRule("analytics_user", 100, 60),
        "insights_user": RateLimitRule("insights_user", 100, 60),
        "authenticated_user": RateLimitRule("authenticated_user", 100, 60),
    }
    values.update(overrides)
    return RateLimitPolicies(**values)


@pytest.mark.anyio
async def test_registration_limit_uses_trusted_client_ip_and_retry_after() -> None:
    limiter = InMemoryRateLimiter()
    policies = roomy_policies(registration_ip=RateLimitRule("registration_ip", 1, 600))
    headers = {"X-Forwarded-For": "203.0.113.10, 10.0.0.1"}
    async with rate_limited_client(
        limiter, policies, trust_proxy_headers=True
    ) as client:
        first = await client.post(
            "/auth/register",
            json={"email": "first@example.com", "password": "long password one"},
            headers=headers,
        )
        blocked = await client.post(
            "/auth/register",
            json={"email": "second@example.com", "password": "long password two"},
            headers=headers,
        )

    assert first.status_code == 201
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "600"
    assert blocked.json() == {
        "error": {
            "code": "rate_limited",
            "message": "request rate limit exceeded",
        }
    }
    assert limiter.calls[:2] == [
        (policies.registration_ip, "ip:203.0.113.10"),
        (policies.registration_ip, "ip:203.0.113.10"),
    ]


@pytest.mark.anyio
async def test_login_limits_normalized_email_separately_from_ip() -> None:
    limiter = InMemoryRateLimiter()
    policies = roomy_policies(login_email=RateLimitRule("login_email", 1, 600))
    async with rate_limited_client(limiter, policies) as client:
        registered = await client.post(
            "/auth/register",
            json={"email": "investor@example.com", "password": "long password one"},
        )
        assert registered.status_code == 201
        first = await client.post(
            "/auth/login",
            json={"email": " INVESTOR@EXAMPLE.COM ", "password": "long password one"},
        )
        blocked = await client.post(
            "/auth/login",
            json={"email": "investor@example.com", "password": "long password one"},
        )

    assert first.status_code == 200
    assert blocked.status_code == 429
    login_calls = [call for call in limiter.calls if call[0].scope.startswith("login")]
    assert login_calls == [
        (policies.login_ip, "ip:127.0.0.1"),
        (policies.login_email, "email:investor@example.com"),
        (policies.login_ip, "ip:127.0.0.1"),
        (policies.login_email, "email:investor@example.com"),
    ]


@pytest.mark.anyio
async def test_authenticated_route_groups_use_their_configured_user_rules() -> None:
    limiter = InMemoryRateLimiter()
    policies = roomy_policies()
    async with rate_limited_client(limiter, policies) as client:
        await client.post(
            "/auth/register",
            json={"email": "owner@example.com", "password": "long password one"},
        )
        login = await client.post(
            "/auth/login",
            json={"email": "owner@example.com", "password": "long password one"},
        )
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        portfolio = await client.post("/portfolios", json={"name": "Limited"})
        portfolio_id = portfolio.json()["id"]
        await client.get(
            f"/portfolios/{portfolio_id}/analytics",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )
        await client.get(f"/portfolios/{portfolio_id}/insights")

    scopes = [rule.scope for rule, _identifier in limiter.calls]
    assert scopes == [
        "registration_ip",
        "login_ip",
        "login_email",
        "authenticated_user",
        "analytics_user",
        "insights_user",
    ]
    user_identifiers = [
        identifier for rule, identifier in limiter.calls if rule.scope.endswith("user")
    ]
    assert len(set(user_identifiers)) == 1


@pytest.mark.anyio
async def test_openapi_documents_rate_limit_responses_and_release_version() -> None:
    limiter = InMemoryRateLimiter()
    async with rate_limited_client(limiter, roomy_policies()) as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    assert document["info"]["version"] == "1.2.0"
    for path, method in (
        ("/auth/register", "post"),
        ("/auth/login", "post"),
        ("/portfolios", "get"),
        ("/portfolios/{portfolio_id}/analytics", "get"),
        ("/portfolios/{portfolio_id}/insights", "post"),
    ):
        assert "429" in document["paths"][path][method]["responses"]


class ScriptedRedis:
    def __init__(self, *results: object) -> None:
        self._results = iter(results)
        self.calls: list[tuple[str, int, tuple[str | int, ...]]] = []

    async def eval(
        self, script: str, numkeys: int, *keys_and_args: str | int
    ) -> object:
        self.calls.append((script, numkeys, keys_and_args))
        result = next(self._results)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.anyio
async def test_redis_limiter_hashes_identifiers_and_enforces_boundary() -> None:
    cache = ScriptedRedis([1, 60], [2, 59])
    limiter = RedisFixedWindowRateLimiter(
        cache,
        "separate-rate-limit-hash-secret-key",
        clock=lambda: 120.0,
    )
    rule = RateLimitRule("login_email", 1, 60)

    await limiter.enforce(rule, "email:private@example.com")
    with pytest.raises(RateLimitExceededError) as captured:
        await limiter.enforce(rule, "email:private@example.com")

    assert captured.value.retry_after_seconds == 59
    serialized_calls = repr(cache.calls)
    assert "private@example.com" not in serialized_calls
    assert "separate-rate-limit-hash-secret-key" not in serialized_calls
    redis_key = cache.calls[0][2][0]
    assert isinstance(redis_key, str)
    assert redis_key.startswith("rate-limit:v1:login_email:2:")


@pytest.mark.anyio
async def test_redis_failure_fails_open_and_logs_no_identifier(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_identifier = "email:private@example.com"
    cache = ScriptedRedis(ConnectionError("redis-secret-response"))
    limiter = RedisFixedWindowRateLimiter(
        cache,
        "separate-rate-limit-hash-secret-key",
    )

    with caplog.at_level(logging.WARNING):
        await limiter.enforce(RateLimitRule("login_email", 1, 60), private_identifier)

    assert "rate_limit_bypass" in caplog.text
    assert private_identifier not in caplog.text
    assert "redis-secret-response" not in caplog.text


def test_default_public_rate_limit_policy_matches_documented_thresholds() -> None:
    policies = RateLimitPolicies()

    assert policies.registration_ip == RateLimitRule("registration_ip", 5, 600)
    assert policies.login_ip == RateLimitRule("login_ip", 10, 600)
    assert policies.login_email == RateLimitRule("login_email", 5, 600)
    assert policies.analytics_user == RateLimitRule("analytics_user", 20, 60)
    assert policies.insights_user == RateLimitRule("insights_user", 10, 60)
    assert policies.authenticated_user == RateLimitRule("authenticated_user", 120, 60)


def test_rate_limit_rule_is_immutable() -> None:
    rule = RateLimitRule("valid", 1, 1)
    with pytest.raises(AttributeError):
        rule.limit = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    "values",
    [("", 1, 1), ("scope", 0, 1), ("scope", 1, 0)],
)
def test_rate_limit_rule_rejects_invalid_values(
    values: tuple[str, int, int],
) -> None:
    with pytest.raises(ValueError):
        RateLimitRule(*values)
