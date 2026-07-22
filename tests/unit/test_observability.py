import asyncio
import io
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from portfolio_analytics_api.api import create_app
from portfolio_analytics_api.application import (
    MarketDataInvalidResponseError,
    MarketDataNotFoundError,
    MarketDataRateLimitError,
    MarketDataResult,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
    UnitOfWork,
)
from portfolio_analytics_api.core import (
    JsonLogFormatter,
    bind_request_id,
    reset_request_id,
)
from portfolio_analytics_api.domain import AnalyticsMethodology, PriceBar
from portfolio_analytics_api.infrastructure import (
    Argon2PasswordHasher,
    FakeMarketDataProvider,
    InMemoryStore,
    InMemoryUnitOfWork,
    JwtAccessTokenService,
    ObservedMarketDataProvider,
)

_JWT_SECRET = "observability-test-secret-key-with-32-characters"


def build_test_app() -> FastAPI:
    store = InMemoryStore()

    def unit_of_work_factory() -> UnitOfWork:
        return InMemoryUnitOfWork(store)

    app = create_app(
        unit_of_work_factory=unit_of_work_factory,
        market_data_provider=FakeMarketDataProvider(
            {"DEMO": (PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),)}
        ),
        methodology=AnalyticsMethodology(
            annual_risk_free_rate=Decimal("0"),
            risk_free_rate_as_of=date(2026, 1, 1),
            risk_free_rate_assumption="Fixed observability test rate.",
        ),
        password_hasher=Argon2PasswordHasher(),
        access_token_service=JwtAccessTokenService(_JWT_SECRET, 30),
    )

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("private-exception-sentinel")

    return app


@contextmanager
def captured_json_logs() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    application_logger = logging.getLogger("portfolio_analytics_api")
    previous_level = application_logger.level
    application_logger.addHandler(handler)
    application_logger.setLevel(logging.INFO)
    try:
        yield stream
    finally:
        application_logger.removeHandler(handler)
        application_logger.setLevel(previous_level)


def parsed_logs(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


@pytest.mark.anyio
async def test_request_ids_are_propagated_and_isolated_across_requests() -> None:
    app = build_test_app()
    transport = httpx.ASGITransport(app=app)
    first_id = "10000000-0000-4000-8000-000000000001"
    second_id = "20000000-0000-4000-8000-000000000002"

    with captured_json_logs() as stream:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            first, second = await asyncio.gather(
                client.get("/health", headers={"X-Request-ID": first_id}),
                client.get("/health", headers={"X-Request-ID": second_id}),
            )

    assert first.headers["X-Request-ID"] == first_id
    assert second.headers["X-Request-ID"] == second_id
    records = parsed_logs(stream)
    for request_id in (first_id, second_id):
        request_records = [
            record for record in records if record.get("request_id") == request_id
        ]
        assert [record["event"] for record in request_records] == [
            "http.request.started",
            "http.request.completed",
        ]
        assert request_records[-1]["http_route"] == "/health"
        assert request_records[-1]["status_code"] == 200


@pytest.mark.anyio
async def test_invalid_request_id_and_sensitive_inputs_are_never_logged() -> None:
    password = "password-secret-sentinel"
    token = "jwt-secret-sentinel"
    api_key = "api-key-secret-sentinel"
    invalid_request_id = "request-id-secret-sentinel"
    app = build_test_app()
    transport = httpx.ASGITransport(app=app)

    with captured_json_logs() as stream:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            registered = await client.post(
                "/auth/register",
                json={"email": "owner@example.com", "password": password},
            )
            duplicate = await client.post(
                "/auth/register",
                json={"email": "owner@example.com", "password": password},
            )
            unauthorized = await client.get(
                "/portfolios/10000000-0000-4000-8000-000000000001",
                headers={"Authorization": f"Bearer {token}"},
            )
            health = await client.get(
                "/health",
                params={"api_key": api_key},
                headers={"X-Request-ID": invalid_request_id},
            )

    assert registered.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["message"] == "email is already registered"
    assert unauthorized.status_code == 401
    assert health.status_code == 200
    UUID(health.headers["X-Request-ID"])
    serialized_logs = stream.getvalue()
    for secret in (password, token, api_key, invalid_request_id):
        assert secret not in serialized_logs


@pytest.mark.anyio
async def test_unhandled_errors_are_generic_and_retain_request_id() -> None:
    request_id = "30000000-0000-4000-8000-000000000003"
    app = build_test_app()
    transport = httpx.ASGITransport(app=app)

    with captured_json_logs() as stream:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/boom", headers={"X-Request-ID": request_id})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == request_id
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "an unexpected error occurred",
        }
    }
    assert "private-exception-sentinel" not in stream.getvalue()
    failed = next(
        record
        for record in parsed_logs(stream)
        if record.get("event") == "http.request.failed"
    )
    assert failed["request_id"] == request_id
    assert failed["error_type"] == "RuntimeError"


class ScriptedProvider:
    def __init__(self, outcome: MarketDataResult | Exception) -> None:
        self._outcome = outcome

    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> MarketDataResult:
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class StepClock:
    def __init__(self, *values: float) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


@pytest.mark.anyio
async def test_provider_latency_and_error_category_are_structured() -> None:
    request_id = "40000000-0000-4000-8000-000000000004"
    result = MarketDataResult((PriceBar("DEMO", date(2026, 1, 2), Decimal("100")),))
    successful = ObservedMarketDataProvider(
        ScriptedProvider(result),
        provider_name="YFinance",
        clock=StepClock(1.0, 1.025),
    )
    failing = ObservedMarketDataProvider(
        ScriptedProvider(MarketDataRateLimitError()),
        provider_name="YFinance",
        clock=StepClock(2.0, 2.01),
    )

    token = bind_request_id(request_id)
    try:
        with captured_json_logs() as stream:
            assert (
                await successful.get_price_bars(
                    "DEMO", date(2026, 1, 1), date(2026, 1, 31)
                )
                == result
            )
            with pytest.raises(MarketDataRateLimitError):
                await failing.get_price_bars(
                    "DEMO", date(2026, 1, 1), date(2026, 1, 31)
                )
    finally:
        reset_request_id(token)

    provider_logs = [
        record
        for record in parsed_logs(stream)
        if record.get("event") == "market_data.provider.request"
    ]
    assert provider_logs[0]["request_id"] == request_id
    assert provider_logs[0]["provider"] == "yfinance"
    assert provider_logs[0]["duration_ms"] == pytest.approx(25.0)
    assert provider_logs[0]["outcome"] == "success"
    assert provider_logs[1]["request_id"] == request_id
    assert provider_logs[1]["duration_ms"] == pytest.approx(10.0)
    assert provider_logs[1]["error_category"] == "rate_limited"
    assert provider_logs[1]["error_type"] == "MarketDataRateLimitError"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "expected_category"),
    [
        (MarketDataTimeoutError(), "timeout"),
        (MarketDataUnavailableError(), "unavailable"),
        (MarketDataNotFoundError("DEMO"), "not_found"),
        (MarketDataInvalidResponseError("invalid"), "invalid_response"),
        (ValueError("invalid"), "invalid_request"),
        (RuntimeError("unexpected"), "unexpected"),
    ],
)
async def test_provider_errors_use_stable_categories(
    error: Exception,
    expected_category: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = ObservedMarketDataProvider(
        ScriptedProvider(error),
        provider_name="yfinance",
        clock=StepClock(1.0, 1.001),
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(type(error)):
            await provider.get_price_bars("DEMO", date(2026, 1, 1), date(2026, 1, 31))

    record = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "market_data.provider.request"
    )
    assert getattr(record, "error_category", None) == expected_category


def test_provider_observation_requires_a_name() -> None:
    with pytest.raises(ValueError, match="provider name"):
        ObservedMarketDataProvider(
            ScriptedProvider(MarketDataUnavailableError()),
            provider_name=" ",
        )


def test_json_formatter_omits_unapproved_sensitive_extra_fields() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="safe message",
        args=(),
        exc_info=None,
    )
    record.password = "password-secret-sentinel"
    record.authorization = "jwt-secret-sentinel"
    record.api_key = "api-key-secret-sentinel"
    formatted = JsonLogFormatter().format(record)

    assert json.loads(formatted)["message"] == "safe message"
    assert "password-secret-sentinel" not in formatted
    assert "jwt-secret-sentinel" not in formatted
    assert "api-key-secret-sentinel" not in formatted
