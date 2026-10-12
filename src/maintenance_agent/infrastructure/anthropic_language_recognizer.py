"""Anthropic-backed implementation of the language-recognition port."""

from anthropic import AsyncAnthropic

from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.prompts.language_recognition import build_language_recognition_prompt


class AnthropicLanguageRecognizer:
    """Use one constrained completion and validate its returned vocabulary."""

    def __init__(
        self,
        client: AsyncAnthropic,
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self._client = client
        self._model = model

    async def recognize(self, description: str) -> LanguageRecognitionResult:
        """Return undetermined for blank descriptions or unsafe provider output."""
        if not description.strip():
            return LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=16,
            messages=[{"role": "user", "content": build_language_recognition_prompt(description)}],
        )
        text = next(
            (block.text for block in response.content if getattr(block, "type", None) == "text"),
            None,
        )
        return LanguageRecognitionResult.from_provider_value(text)
