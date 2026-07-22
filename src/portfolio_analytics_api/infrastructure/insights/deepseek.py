import asyncio
import re

from openai import APIError, AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from portfolio_analytics_api.application import InsightGenerationError
from portfolio_analytics_api.domain import GeneratedInsight, InsightInput
from portfolio_analytics_api.infrastructure.insights.serialization import (
    serialize_insight_input,
)

_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_FORBIDDEN_RECOMMENDATION = re.compile(
    r"\b(buy|sell|purchase|liquidate|guarantee|guaranteed)\b",
    re.IGNORECASE,
)
_SYSTEM_PROMPT = """\
You explain portfolio risk from supplied structured analytics JSON.
Do not calculate or invent metrics. Do not predict prices or returns. Do not
recommend transactions and do not use the words buy, sell, purchase, liquidate,
guarantee, or guaranteed. Return JSON only, with exactly this shape:
{"summary":"concise historical risk explanation",
 "additional_limitations":["zero to three input-specific limitations"]}
The summary must distinguish historical evidence from forecasts. Do not include
a disclaimer; the application appends its fixed disclaimer.
"""


class _DeepSeekOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=20, max_length=1200)
    additional_limitations: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def reject_transaction_recommendations(self) -> "_DeepSeekOutput":
        text = " ".join((self.summary, *self.additional_limitations))
        if _FORBIDDEN_RECOMMENDATION.search(text):
            raise ValueError("generated insight contains transaction language")
        if any(not limitation.strip() for limitation in self.additional_limitations):
            raise ValueError("generated limitations must not be empty")
        return self


class DeepSeekInsightGenerator:
    def __init__(
        self,
        api_key: str,
        model_name: str = "deepseek-v4-flash",
        timeout_seconds: float = 8.0,
        prompt_version: str = "deepseek-risk-summary-v1",
        client: AsyncOpenAI | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("DeepSeek API key must not be empty")
        if not model_name.strip() or not prompt_version.strip():
            raise ValueError("DeepSeek model and prompt version must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("DeepSeek timeout must be positive")
        self._model_name = model_name.strip()
        self._prompt_version = prompt_version.strip()
        self._timeout_seconds = timeout_seconds
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=_DEEPSEEK_BASE_URL,
            timeout=timeout_seconds,
            max_retries=0,
        )

    @property
    def generator_name(self) -> str:
        return "deepseek"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    async def generate(self, insight_input: InsightInput) -> GeneratedInsight:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.chat.completions.create(
                    model=self._model_name,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                "Explain this structured analytics JSON without "
                                "adding facts:\n"
                                f"{serialize_insight_input(insight_input)}"
                            ),
                        },
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=600,
                    stream=False,
                    extra_body={"thinking": {"type": "disabled"}},
                )
        except (TimeoutError, APIError) as error:
            raise InsightGenerationError("DeepSeek request failed") from error

        if not response.choices or response.choices[0].finish_reason != "stop":
            raise InsightGenerationError("DeepSeek response did not complete")
        content = response.choices[0].message.content
        if not content:
            raise InsightGenerationError("DeepSeek response was empty")
        try:
            parsed = _DeepSeekOutput.model_validate_json(content)
        except ValidationError as error:
            raise InsightGenerationError(
                "DeepSeek response failed structured validation"
            ) from error
        return GeneratedInsight(
            summary=parsed.summary.strip(),
            additional_limitations=tuple(
                limitation.strip() for limitation in parsed.additional_limitations
            ),
        )

    async def aclose(self) -> None:
        await self._client.close()
