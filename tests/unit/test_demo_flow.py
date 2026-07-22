from datetime import date
from typing import Any
from uuid import uuid4

import httpx
import pytest
from scripts.demo_flow import DemoConfig, DemoError, run_demo


def _response(status_code: int, json: Any) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=json,
        headers={"X-Request-ID": str(uuid4())},
    )


def test_demo_runs_owned_idempotent_analytics_and_insight_flow() -> None:
    buy_id = str(uuid4())
    portfolio_id = str(uuid4())
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/health":
            return _response(200, {"status": "ok"})
        if request.url.path == "/auth/register":
            return _response(201, {"id": str(uuid4()), "email": "demo@example.com"})
        if request.url.path == "/auth/login":
            return _response(
                200,
                {
                    "access_token": "safe-test-token",
                    "token_type": "bearer",
                    "expires_in": 1800,
                },
            )
        if request.url.path == "/portfolios" and request.method == "POST":
            assert request.headers["Authorization"] == "Bearer safe-test-token"
            return _response(
                201,
                {
                    "id": portfolio_id,
                    "name": "V1 release candidate demo",
                    "base_currency": "USD",
                },
            )
        if request.url.path == f"/portfolios/{portfolio_id}":
            return _response(
                200,
                {
                    "id": portfolio_id,
                    "name": "V1 release candidate demo",
                    "base_currency": "USD",
                },
            )
        if request.url.path.endswith("/transactions"):
            if request.method == "GET":
                return _response(200, [{"id": str(uuid4())}, {"id": buy_id}])
            payload = request.content.decode()
            if "demo-deposit-001" in payload:
                return _response(201, {"id": str(uuid4())})
            previous_buy_calls = sum(
                1
                for method, path in calls
                if method == "POST" and path.endswith("/transactions")
            )
            return _response(200 if previous_buy_calls == 3 else 201, {"id": buy_id})
        if request.url.path.endswith("/analytics"):
            return _response(
                200,
                {
                    "as_of": "2026-01-30",
                    "simple_return": 0.05,
                    "annualized_volatility": 0.2,
                    "max_drawdown": -0.1,
                    "sharpe_ratio": 0.5,
                    "portfolio_value": "1100.00",
                    "stale": False,
                },
            )
        if request.url.path.endswith("/insights"):
            return _response(
                200,
                {
                    "risk_level": "moderate",
                    "generator": "deterministic_rules",
                    "prompt_version": "risk-rules-v1",
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="http://test") as client:
        result = run_demo(
            client,
            DemoConfig(
                base_url="http://test",
                email="demo@example.com",
                password="a-long-demo-password",
                symbol="aapl",
                start_date=date(2026, 1, 2),
                end_date=date(2026, 1, 30),
            ),
        )

    assert result["portfolio_id"] == portfolio_id
    assert result["transaction_count"] == 2
    assert result["idempotent_replay"] is True
    assert result["insight"] == {
        "risk_level": "moderate",
        "generator": "deterministic_rules",
        "prompt_version": "risk-rules-v1",
    }
    assert ("GET", f"/portfolios/{portfolio_id}") in calls


def test_demo_rejects_response_without_request_id() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"status": "ok"})
    )
    with httpx.Client(transport=transport, base_url="http://test") as client:
        with pytest.raises(DemoError, match="did not return a UUID request ID"):
            run_demo(
                client,
                DemoConfig(
                    base_url="http://test",
                    email="demo@example.com",
                    password="a-long-demo-password",
                    symbol="AAPL",
                    start_date=date(2026, 1, 2),
                    end_date=date(2026, 1, 30),
                ),
            )
