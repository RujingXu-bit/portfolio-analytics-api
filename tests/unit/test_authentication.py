from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import httpx
import pytest

from portfolio_analytics_api.api import create_app
from portfolio_analytics_api.application import InvalidAccessTokenError, UnitOfWork
from portfolio_analytics_api.domain import AnalyticsMethodology
from portfolio_analytics_api.infrastructure import (
    Argon2PasswordHasher,
    FakeMarketDataProvider,
    InMemoryStore,
    InMemoryUnitOfWork,
    JwtAccessTokenService,
)

_SECRET_KEY = "authentication-unit-test-secret-key-32-characters"
_PASSWORD = "correct horse battery staple"


@asynccontextmanager
async def auth_client() -> AsyncIterator[tuple[httpx.AsyncClient, InMemoryStore]]:
    store = InMemoryStore()

    def unit_of_work_factory() -> UnitOfWork:
        return InMemoryUnitOfWork(store)

    app = create_app(
        unit_of_work_factory=unit_of_work_factory,
        market_data_provider=FakeMarketDataProvider({}),
        methodology=AnalyticsMethodology(
            annual_risk_free_rate=Decimal("0"),
            risk_free_rate_as_of=date(2026, 1, 1),
            risk_free_rate_assumption="Fixed offline test rate.",
        ),
        password_hasher=Argon2PasswordHasher(),
        access_token_service=JwtAccessTokenService(_SECRET_KEY, expire_minutes=30),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, store


@pytest.mark.anyio
async def test_register_and_login_hash_password_and_issue_verifiable_token() -> None:
    async with auth_client() as (client, store):
        registration = await client.post(
            "/auth/register",
            json={"email": "  Investor@Example.COM ", "password": _PASSWORD},
        )
        login = await client.post(
            "/auth/login",
            json={"email": "investor@example.com", "password": _PASSWORD},
        )

    assert registration.status_code == 201
    registered = registration.json()
    user_id = UUID(registered["id"])
    assert registered == {"id": str(user_id), "email": "investor@example.com"}
    stored_user = store.users[user_id]
    assert stored_user.password_hash != _PASSWORD
    assert stored_user.password_hash.startswith("$argon2")

    assert login.status_code == 200
    token_body = login.json()
    assert token_body["token_type"] == "bearer"
    assert token_body["expires_in"] == 1800
    assert (
        JwtAccessTokenService(_SECRET_KEY, 30).verify(token_body["access_token"])
        == user_id
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("investor@example.com", "wrong password"),
        ("missing@example.com", _PASSWORD),
    ],
)
async def test_invalid_login_uses_one_safe_authentication_error(
    email: str, password: str
) -> None:
    async with auth_client() as (client, _store):
        await client.post(
            "/auth/register",
            json={"email": "investor@example.com", "password": _PASSWORD},
        )
        response = await client.post(
            "/auth/login", json={"email": email, "password": password}
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "error": {
            "code": "authentication_failed",
            "message": "authentication failed",
        }
    }


@pytest.mark.anyio
async def test_duplicate_normalized_email_is_rejected() -> None:
    async with auth_client() as (client, _store):
        first = await client.post(
            "/auth/register",
            json={"email": "investor@example.com", "password": _PASSWORD},
        )
        duplicate = await client.post(
            "/auth/register",
            json={"email": " INVESTOR@example.com ", "password": _PASSWORD},
        )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_already_registered"


def test_expired_access_token_is_rejected() -> None:
    expired_issuer = JwtAccessTokenService(
        _SECRET_KEY,
        expire_minutes=1,
        clock=lambda: datetime.now(UTC) - timedelta(minutes=2),
    )
    token = expired_issuer.issue(UUID("00000000-0000-0000-0000-000000000001"))

    with pytest.raises(InvalidAccessTokenError):
        expired_issuer.verify(token)
