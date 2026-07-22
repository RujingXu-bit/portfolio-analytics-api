import os
from datetime import date
from decimal import Decimal

import pytest

from portfolio_analytics_api.core import Settings
from portfolio_analytics_api.domain import (
    AnalyticsMethodology,
    AssetWeight,
    InsightInput,
    validate_generated_insight,
)
from portfolio_analytics_api.infrastructure import DeepSeekInsightGenerator

pytestmark = pytest.mark.contract


@pytest.mark.anyio
async def test_deepseek_returns_valid_structured_risk_narrative() -> None:
    if os.getenv("RUN_DEEPSEEK_CONTRACT") != "1":
        pytest.skip("set RUN_DEEPSEEK_CONTRACT=1 to call the real DeepSeek API")
    settings = Settings()
    if settings.deepseek_api_key is None:
        pytest.skip("DEEPSEEK_API_KEY is not configured")
    api_key = settings.deepseek_api_key.get_secret_value()
    if not api_key:
        pytest.skip("DEEPSEEK_API_KEY is empty")

    generator = DeepSeekInsightGenerator(
        api_key=api_key,
        model_name=settings.deepseek_model,
        timeout_seconds=settings.deepseek_timeout_seconds,
    )
    try:
        generated = await generator.generate(
            InsightInput(
                as_of=date(2026, 1, 30),
                simple_return=0.05,
                annualized_volatility=0.2,
                max_drawdown=-0.1,
                sharpe_ratio=0.6,
                asset_weights=(AssetWeight("DEMO", Decimal("700"), Decimal("0.7")),),
                methodology=AnalyticsMethodology(
                    annual_risk_free_rate=Decimal("0.04"),
                    risk_free_rate_as_of=date(2026, 1, 1),
                    risk_free_rate_assumption="Fixed contract-test rate.",
                ),
                stale=False,
            )
        )
    finally:
        await generator.aclose()

    validate_generated_insight(generated)
