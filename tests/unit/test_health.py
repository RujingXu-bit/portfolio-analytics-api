import httpx
import pytest


@pytest.mark.anyio
async def test_health_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JWT_SECRET_KEY", "health-test-secret-key-with-at-least-32-characters"
    )
    from portfolio_analytics_api.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
