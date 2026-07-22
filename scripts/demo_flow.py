import argparse
import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import httpx


class DemoError(RuntimeError):
    """Raised when the public demo flow cannot complete safely."""


@dataclass(frozen=True)
class DemoConfig:
    base_url: str
    email: str
    password: str
    other_email: str
    other_password: str
    symbol: str
    start_date: date
    end_date: date


def run_demo(client: httpx.Client, config: DemoConfig) -> dict[str, object]:
    if config.start_date >= config.end_date:
        raise DemoError("start date must be before end date")

    _request(client, "GET", "/health", expected_status=200)
    _request(
        client,
        "POST",
        "/auth/register",
        expected_status=201,
        json={"email": config.email, "password": config.password},
    )
    login = _json_object(
        _request(
            client,
            "POST",
            "/auth/login",
            expected_status=200,
            json={"email": config.email, "password": config.password},
        )
    )
    access_token = login.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise DemoError("login response did not contain an access token")
    headers = {"Authorization": f"Bearer {access_token}"}

    portfolio = _json_object(
        _request(
            client,
            "POST",
            "/portfolios",
            expected_status=201,
            headers=headers,
            json={"name": "V1 release demo", "base_currency": "USD"},
        )
    )
    portfolio_id = _required_string(portfolio, "id")
    portfolio_path = f"/portfolios/{portfolio_id}"
    _request(client, "GET", portfolio_path, expected_status=200, headers=headers)
    portfolio_page = _json_object(
        _request(client, "GET", "/portfolios", expected_status=200, headers=headers)
    )
    portfolio_listed = any(
        isinstance(item, dict) and item.get("id") == portfolio_id
        for item in _required_array(portfolio_page, "items")
    )
    if not portfolio_listed:
        raise DemoError("created portfolio did not appear in the owner-scoped list")

    start = config.start_date.isoformat()
    deposit_payload = {
        "external_id": "demo-deposit-001",
        "transaction_type": "DEPOSIT",
        "occurred_at": f"{start}T08:00:00Z",
        "cash_amount": "1000",
        "fees": "0",
    }
    buy_payload = {
        "external_id": "demo-buy-001",
        "transaction_type": "BUY",
        "occurred_at": f"{start}T09:00:00Z",
        "symbol": config.symbol.upper(),
        "quantity": "2",
        "unit_price": "100",
        "fees": "1",
    }
    transaction_path = f"{portfolio_path}/transactions"
    _request(
        client,
        "POST",
        transaction_path,
        expected_status=201,
        headers=headers,
        json=deposit_payload,
    )
    created_buy = _json_object(
        _request(
            client,
            "POST",
            transaction_path,
            expected_status=201,
            headers=headers,
            json=buy_payload,
        )
    )
    replayed_buy = _json_object(
        _request(
            client,
            "POST",
            transaction_path,
            expected_status=200,
            headers=headers,
            json=buy_payload,
        )
    )
    idempotent_replay = _required_string(created_buy, "id") == _required_string(
        replayed_buy, "id"
    )
    if not idempotent_replay:
        raise DemoError("idempotent transaction replay returned a different record")

    transactions = _json_array(
        _request(
            client,
            "GET",
            transaction_path,
            expected_status=200,
            headers=headers,
        )
    )
    query = {
        "start_date": config.start_date.isoformat(),
        "end_date": config.end_date.isoformat(),
    }
    analytics = _json_object(
        _request(
            client,
            "GET",
            f"{portfolio_path}/analytics",
            expected_status=200,
            headers=headers,
            params=query,
        )
    )
    insight = _json_object(
        _request(
            client,
            "POST",
            f"{portfolio_path}/insights",
            expected_status=200,
            headers=headers,
            params=query,
        )
    )
    if (
        insight.get("generator") != "deterministic_rules"
        or insight.get("model_name") is not None
    ):
        raise DemoError("public insight did not use the deterministic fallback")
    snapshot_page = _json_object(
        _request(
            client,
            "GET",
            f"{portfolio_path}/insights",
            expected_status=200,
            headers=headers,
        )
    )
    snapshots = _required_array(snapshot_page, "items")
    snapshot_persisted = any(
        isinstance(item, dict)
        and item.get("as_of") == insight.get("as_of")
        and item.get("generator") == insight.get("generator")
        and item.get("prompt_version") == insight.get("prompt_version")
        for item in snapshots
    )
    if not snapshot_persisted:
        raise DemoError("generated insight did not appear in snapshot history")

    _request(
        client,
        "POST",
        "/auth/register",
        expected_status=201,
        json={"email": config.other_email, "password": config.other_password},
    )
    other_login = _json_object(
        _request(
            client,
            "POST",
            "/auth/login",
            expected_status=200,
            json={"email": config.other_email, "password": config.other_password},
        )
    )
    other_access_token = other_login.get("access_token")
    if not isinstance(other_access_token, str) or not other_access_token:
        raise DemoError("second login response did not contain an access token")
    other_headers = {"Authorization": f"Bearer {other_access_token}"}
    foreign_response = _request(
        client,
        "GET",
        portfolio_path,
        expected_status=404,
        headers=other_headers,
    )
    missing_response = _request(
        client,
        "GET",
        f"/portfolios/{uuid4()}",
        expected_status=404,
        headers=other_headers,
    )
    ownership_isolated = (
        _error_code(foreign_response)
        == _error_code(missing_response)
        == "portfolio_not_found"
    )
    if not ownership_isolated:
        raise DemoError("cross-user and missing Portfolio errors did not match")

    return {
        "portfolio_id": portfolio_id,
        "portfolio_listed": portfolio_listed,
        "transaction_count": len(transactions),
        "idempotent_replay": idempotent_replay,
        "snapshot_history_count": len(snapshots),
        "snapshot_persisted": snapshot_persisted,
        "ownership_isolated": ownership_isolated,
        "analytics": {
            "as_of": analytics.get("as_of"),
            "simple_return": analytics.get("simple_return"),
            "annualized_volatility": analytics.get("annualized_volatility"),
            "max_drawdown": analytics.get("max_drawdown"),
            "sharpe_ratio": analytics.get("sharpe_ratio"),
            "portfolio_value": analytics.get("portfolio_value"),
            "stale": analytics.get("stale"),
        },
        "insight": {
            "risk_level": insight.get("risk_level"),
            "generator": insight.get("generator"),
            "prompt_version": insight.get("prompt_version"),
        },
    }


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected_status: int,
    **kwargs: Any,
) -> httpx.Response:
    try:
        response = client.request(method, path, **kwargs)
    except httpx.HTTPError as error:
        raise DemoError(f"{method} {path} could not reach the API") from error
    if response.status_code != expected_status:
        error_code = "unknown_error"
        try:
            body = response.json()
            if isinstance(body, dict):
                error_body = body.get("error")
                if isinstance(error_body, dict) and isinstance(
                    error_body.get("code"), str
                ):
                    error_code = error_body["code"]
        except ValueError:
            pass
        raise DemoError(
            f"{method} {path} returned {response.status_code} ({error_code})"
        )
    request_id = response.headers.get("X-Request-ID")
    try:
        UUID(request_id or "")
    except ValueError as error:
        raise DemoError(f"{method} {path} did not return a UUID request ID") from error
    return response


def _json_object(response: httpx.Response) -> dict[str, Any]:
    body = response.json()
    if not isinstance(body, dict):
        raise DemoError("API response was not a JSON object")
    return body


def _json_array(response: httpx.Response) -> list[Any]:
    body = response.json()
    if not isinstance(body, list):
        raise DemoError("API response was not a JSON array")
    return body


def _required_string(body: dict[str, Any], field: str) -> str:
    value = body.get(field)
    if not isinstance(value, str) or not value:
        raise DemoError(f"API response did not contain {field}")
    return value


def _required_array(body: dict[str, Any], field: str) -> list[Any]:
    value = body.get(field)
    if not isinstance(value, list):
        raise DemoError(f"API response did not contain a list field named {field}")
    return value


def _error_code(response: httpx.Response) -> str | None:
    body = _json_object(response)
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the V1 release flow through public HTTP APIs."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument(
        "--start-date", type=date.fromisoformat, default=date(2026, 1, 2)
    )
    parser.add_argument(
        "--end-date", type=date.fromisoformat, default=date(2026, 1, 30)
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    suffix = uuid4().hex
    config = DemoConfig(
        base_url=args.base_url,
        email=args.email or f"v1-demo-{suffix}@example.com",
        password=f"v1-demo-password-{suffix}",
        other_email=f"v1-demo-other-{suffix}@example.com",
        other_password=f"v1-demo-other-password-{suffix}",
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    try:
        with httpx.Client(base_url=config.base_url, timeout=20.0) as client:
            result = run_demo(client, config)
    except DemoError as error:
        raise SystemExit(f"Demo failed: {error}") from error
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
