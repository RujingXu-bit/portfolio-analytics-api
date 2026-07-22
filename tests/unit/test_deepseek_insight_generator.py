import json
from datetime import date
from decimal import Decimal
from typing import cast

import httpx
import pytest
from openai import AsyncOpenAI

from portfolio_analytics_api.application import InsightGenerationError
from portfolio_analytics_api.domain import (
    AnalyticsMethodology,
    AssetWeight,
    InsightInput,
)
from portfolio_analytics_api.infrastructure import DeepSeekInsightGenerator


def insight_input() -> InsightInput:
    return InsightInput(
        as_of=date(2026, 1, 30),
        simple_return=0.05,
        annualized_volatility=0.2,
        max_drawdown=-0.1,
        sharpe_ratio=0.6,
        asset_weights=(AssetWeight("DEMO", Decimal("700"), Decimal("0.7")),),
        methodology=AnalyticsMethodology(
            annual_risk_free_rate=Decimal("0.04"),
            risk_free_rate_as_of=date(2026, 1, 1),
            risk_free_rate_assumption="Fixed provider-test rate.",
        ),
        stale=False,
    )


def build_generator(
    output_content: str,
) -> tuple[DeepSeekInsightGenerator, list[bytes]]:
    requests: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.content)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1784690000,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": output_content,
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    client = AsyncOpenAI(
        api_key="test-only-key",
        base_url="https://api.deepseek.com",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return (
        DeepSeekInsightGenerator(
            api_key="test-only-key",
            client=client,
        ),
        requests,
    )


@pytest.mark.anyio
async def test_deepseek_uses_only_structured_input_and_validates_json() -> None:
    generator, requests = build_generator(
        json.dumps(
            {
                "summary": (
                    "Historical metrics indicate elevated variability and "
                    "concentration."
                ),
                "additional_limitations": ["The observation window is limited."],
            }
        )
    )
    try:
        result = await generator.generate(insight_input())
    finally:
        await generator.aclose()

    assert result.summary.startswith("Historical metrics")
    assert result.additional_limitations == ("The observation window is limited.",)
    request_body = cast(dict[str, object], json.loads(requests[0]))
    assert request_body["model"] == "deepseek-v4-flash"
    assert request_body["response_format"] == {"type": "json_object"}
    assert request_body["thinking"] == {"type": "disabled"}
    messages = cast(list[dict[str, str]], request_body["messages"])
    structured_payload = cast(
        dict[str, object], json.loads(messages[1]["content"].split(":\n", 1)[1])
    )
    assert set(structured_payload) == {"metrics", "methodology"}
    metrics = cast(dict[str, object], structured_payload["metrics"])
    assert set(metrics) == {
        "annualized_volatility",
        "as_of",
        "asset_weights",
        "max_drawdown",
        "sharpe_ratio",
        "simple_return",
        "stale",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "output_content",
    [
        "not-json",
        json.dumps(
            {
                "summary": "This output contains an unsupported extra field.",
                "additional_limitations": [],
                "extra": "not allowed",
            }
        ),
        json.dumps(
            {
                "summary": "The user should buy this concentrated portfolio now.",
                "additional_limitations": [],
            }
        ),
    ],
)
async def test_deepseek_rejects_invalid_or_unsafe_output(output_content: str) -> None:
    generator, _requests = build_generator(output_content)
    try:
        with pytest.raises(InsightGenerationError):
            await generator.generate(insight_input())
    finally:
        await generator.aclose()
