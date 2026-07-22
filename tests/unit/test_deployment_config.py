from pathlib import Path


def test_render_blueprint_uses_runtime_and_safe_secret_placeholders() -> None:
    blueprint = Path("render.yaml").read_text(encoding="utf-8")

    for required in (
        "runtime: docker",
        "plan: starter",
        "region: frankfurt",
        "autoDeployTrigger: checksPass",
        "preDeployCommand: uv run alembic upgrade head",
        "healthCheckPath: /health",
        "MARKET_DATA_PROVIDER",
        "RATE_LIMIT_TRUST_PROXY_HEADERS",
        "generateValue: true",
    ):
        assert required in blueprint

    assert "--host 0.0.0.0" in blueprint
    assert "--port $PORT" in blueprint
    assert "${PORT:-10000}" not in blueprint
    assert "sh -c" not in blueprint
    assert "DEEPSEEK_API_KEY" not in blueprint
    assert "postgresql+asyncpg://" not in blueprint
    assert "rediss://" not in blueprint


def test_public_deployment_runbook_preserves_security_boundaries() -> None:
    runbook = Path("docs/deployment.md").read_text(encoding="utf-8")

    for required in (
        "Do not enter real financial or sensitive information",
        "rate_limit_bypass",
        "Do not run `alembic downgrade` automatically",
        "not a production SLA",
        "Do not configure `DEEPSEEK_API_KEY`",
    ):
        assert required in runbook.replace("\n", " ")
