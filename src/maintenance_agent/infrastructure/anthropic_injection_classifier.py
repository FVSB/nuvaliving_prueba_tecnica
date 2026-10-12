"""Anthropic-backed evidence provider for the inbound prompt-injection guard."""

from typing import Literal

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ConfigDict, Field

from maintenance_agent.application.injection_guard import InjectionAssessment
from maintenance_agent.infrastructure.anthropic_conversation import _structured_output
from maintenance_agent.prompts.injection_guard import build_assess_prompt, build_extract_prompt


class _AssessmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: Literal["yes", "no"]
    probability_yes: float = Field(ge=0.0, le=1.0)


class _FragmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fragment: str


_ASSESSMENT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "enum": ["yes", "no"]},
        "probability_yes": {"type": "number"},
    },
    "required": ["answer", "probability_yes"],
    "additionalProperties": False,
}

_FRAGMENT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"fragment": {"type": "string"}},
    "required": ["fragment"],
    "additionalProperties": False,
}


class AnthropicInjectionClassifier:
    """Self-reported probability only: the API exposes no token log-probabilities."""

    def __init__(self, client: AsyncAnthropic, model: str = "claude-haiku-5-5") -> None:
        self._client = client
        self._model = model

    async def _call(self, prompt: str, schema: dict[str, object], max_tokens: int):
        return await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "disabled"},
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )

    async def assess(self, text: str) -> InjectionAssessment:
        response = await self._call(build_assess_prompt(text), _ASSESSMENT_SCHEMA, 200)
        output = _structured_output(response, _AssessmentOutput, "injection_assess")
        return InjectionAssessment(output.answer == "yes", output.probability_yes)

    async def extract_fragment(self, text: str) -> str:
        response = await self._call(build_extract_prompt(text), _FRAGMENT_SCHEMA, 1000)
        return _structured_output(response, _FragmentOutput, "injection_extract").fragment
