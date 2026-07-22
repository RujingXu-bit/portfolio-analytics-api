import asyncio
import json
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

import httpx
import locust
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from benchmarks.fixture import (
    BENCHMARK_SYMBOL,
    MAX_WINDOW_DAYS,
    MIN_WINDOW_DAYS,
    PRICE_BAR_COUNT,
    PRICE_BARS,
    hot_query_window,
)
from benchmarks.reporting import (
    ApplicationMetrics,
    LocustMetrics,
    read_json_log_slice,
    read_locust_metrics,
    summarize_application_logs,
)
from portfolio_analytics_api.core import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIRECTORY = PROJECT_ROOT / ".artifacts" / "load-test"
HOST = "127.0.0.1"
PORT = 8099
USERS = int(os.environ.get("BENCHMARK_USERS", "10"))
SPAWN_RATE = float(os.environ.get("BENCHMARK_SPAWN_RATE", "2"))
RUN_TIME_SECONDS = int(os.environ.get("BENCHMARK_RUN_TIME_SECONDS", "60"))


class ScenarioResult(TypedDict):
    locust: LocustMetrics
    application: ApplicationMetrics


async def _reset_test_database(database_url: str) -> None:
    database_name = make_url(database_url).database or ""
    if not database_name.endswith("_test"):
        raise RuntimeError("refusing to reset a database without an _test suffix")
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


def _run_migrations(database_url: str) -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    command.check(config)


def _wait_for_app(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("benchmark application exited before becoming ready")
        try:
            response = httpx.get(f"{base_url}/health", timeout=1)
        except httpx.HTTPError:
            time.sleep(0.2)
            continue
        if response.status_code == 200:
            return
        time.sleep(0.2)
    raise RuntimeError("benchmark application did not become ready within 30 seconds")


def _seed_benchmark(base_url: str) -> tuple[str, str]:
    email = "load-test@example.com"
    password = "local synthetic load password"
    with httpx.Client(base_url=base_url, timeout=10) as client:
        registration = client.post(
            "/auth/register", json={"email": email, "password": password}
        )
        registration.raise_for_status()
        login = client.post("/auth/login", json={"email": email, "password": password})
        login.raise_for_status()
        token = str(login.json()["access_token"])
        headers = {"Authorization": f"Bearer {token}"}
        portfolio = client.post(
            "/portfolios",
            headers=headers,
            json={"name": "Synthetic load portfolio", "base_currency": "USD"},
        )
        portfolio.raise_for_status()
        portfolio_id = str(portfolio.json()["id"])
        transaction = client.post(
            f"/portfolios/{portfolio_id}/transactions",
            headers=headers,
            json={
                "external_id": "load-buy-001",
                "transaction_type": "BUY",
                "occurred_at": f"{PRICE_BARS[0].date.isoformat()}T09:00:00Z",
                "symbol": BENCHMARK_SYMBOL,
                "quantity": "10",
                "unit_price": "100",
                "fees": "0",
            },
        )
        transaction.raise_for_status()
    return token, portfolio_id


def _prewarm_hot_query(base_url: str, token: str, portfolio_id: str) -> None:
    start_date, end_date = hot_query_window()
    response = httpx.get(
        f"{base_url}/portfolios/{portfolio_id}/analytics",
        params={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    response.raise_for_status()


def _run_scenario(
    scenario: str,
    base_url: str,
    token: str,
    portfolio_id: str,
    app_log_path: Path,
) -> ScenarioResult:
    log_offset = app_log_path.stat().st_size
    environment = {
        **os.environ,
        "BENCHMARK_ACCESS_TOKEN": token,
        "BENCHMARK_PORTFOLIO_ID": portfolio_id,
        "BENCHMARK_SCENARIO": scenario,
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "locust",
            "-f",
            str(PROJECT_ROOT / "benchmarks" / "locustfile.py"),
            "--headless",
            "--users",
            str(USERS),
            "--spawn-rate",
            str(SPAWN_RATE),
            "--run-time",
            f"{RUN_TIME_SECONDS}s",
            "--stop-timeout",
            "5",
            "--host",
            base_url,
            "--json",
            "--skip-log",
            "--exit-code-on-error",
            "1",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=RUN_TIME_SECONDS + 90,
        check=False,
    )
    locust_result_path = ARTIFACT_DIRECTORY / f"{scenario}-final.json"
    locust_result_path.write_text(
        completed.stdout,
        encoding="utf-8",
    )
    (ARTIFACT_DIRECTORY / f"{scenario}-locust-errors.txt").write_text(
        completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{scenario} Locust run failed: {completed.stderr}")
    time.sleep(0.5)
    locust_metrics = read_locust_metrics(locust_result_path)
    application_metrics = summarize_application_logs(
        read_json_log_slice(app_log_path, log_offset)
    )
    _validate_scenario(scenario, locust_metrics, application_metrics)
    return {"locust": locust_metrics, "application": application_metrics}


def _validate_scenario(
    scenario: str,
    locust_metrics: LocustMetrics,
    application_metrics: ApplicationMetrics,
) -> None:
    request_count = locust_metrics["request_count"]
    if request_count <= 0 or locust_metrics["failure_count"] != 0:
        raise RuntimeError(f"{scenario} benchmark did not complete without errors")
    if scenario == "cold":
        if (
            application_metrics["cache_hits"] != 0
            or application_metrics["cache_misses"] != request_count
            or application_metrics["provider_calls"] != request_count
        ):
            raise RuntimeError("cold benchmark did not sustain cache misses")
    elif (
        application_metrics["cache_hits"] != request_count
        or application_metrics["cache_misses"] != 0
        or application_metrics["provider_calls"] != 0
    ):
        raise RuntimeError("hot benchmark did not remain fully cache-backed")


def _print_summary(results: dict[str, ScenarioResult]) -> None:
    print("Scenario | Requests | P50 ms | P95 ms | RPS | Errors | Cache hit")
    print("--- | ---: | ---: | ---: | ---: | ---: | ---:")
    for scenario in ("cold", "hot"):
        result = results[scenario]
        locust_metrics = result["locust"]
        application_metrics = result["application"]
        print(
            f"{scenario} | {locust_metrics['request_count']} | "
            f"{locust_metrics['p50_ms']:.3f} | {locust_metrics['p95_ms']:.3f} | "
            f"{locust_metrics['requests_per_second']:.3f} | "
            f"{locust_metrics['failure_count']} | "
            f"{application_metrics['cache_hit_rate_percent']:.3f}%"
        )


def main() -> None:
    if USERS <= 0 or SPAWN_RATE <= 0 or RUN_TIME_SECONDS <= 0:
        raise RuntimeError("benchmark users, spawn rate, and run time must be positive")
    settings = Settings()
    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    asyncio.run(_reset_test_database(settings.test_database_url))
    _run_migrations(settings.test_database_url)

    cache_namespace = f"benchmark-{uuid4().hex}"
    app_log_path = ARTIFACT_DIRECTORY / "application.jsonl"
    environment = {
        **os.environ,
        "BENCHMARK_CACHE_NAMESPACE": cache_namespace,
    }
    base_url = f"http://{HOST}:{PORT}"
    with app_log_path.open("w", encoding="utf-8") as app_log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "benchmarks.app:app",
                "--host",
                HOST,
                "--port",
                str(PORT),
                "--no-access-log",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=app_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_for_app(base_url, process)
            token, portfolio_id = _seed_benchmark(base_url)
            results: dict[str, ScenarioResult] = {}
            results["cold"] = _run_scenario(
                "cold", base_url, token, portfolio_id, app_log_path
            )
            _prewarm_hot_query(base_url, token, portfolio_id)
            time.sleep(0.5)
            results["hot"] = _run_scenario(
                "hot", base_url, token, portfolio_id, app_log_path
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    result_document = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "locust": locust.__version__,
            "uvicorn_workers": 1,
            "provider": "deterministic fixture with 50ms delay",
            "database": "PostgreSQL 16 disposable _test database",
            "cache": "Redis 7 isolated benchmark namespace",
        },
        "workload": {
            "users": USERS,
            "spawn_rate_per_second": SPAWN_RATE,
            "run_time_seconds_per_scenario": RUN_TIME_SECONDS,
            "portfolio_count": 1,
            "transaction_count": 1,
            "symbol_count": 1,
            "price_bar_count": PRICE_BAR_COUNT,
            "cold_window_days": [MIN_WINDOW_DAYS, MAX_WINDOW_DAYS],
            "hot_window_days": MAX_WINDOW_DAYS,
        },
        "results": results,
    }
    (ARTIFACT_DIRECTORY / "results.json").write_text(
        json.dumps(result_document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _print_summary(results)
    print(f"Detailed results: {ARTIFACT_DIRECTORY / 'results.json'}")


if __name__ == "__main__":
    main()
