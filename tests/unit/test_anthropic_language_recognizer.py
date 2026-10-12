from types import SimpleNamespace

from maintenance_agent.domain.languages import LanguageCode
from maintenance_agent.infrastructure.anthropic_language_recognizer import (
    AnthropicLanguageRecognizer,
)


class FakeMessages:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.calls = 0

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls += 1
        self.last_kwargs = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._response_text)])


class FakeClient:
    def __init__(self, response_text: str) -> None:
        self.messages = FakeMessages(response_text)


async def test_recognizer_validates_provider_language_code() -> None:
    client = FakeClient("es")
    recognizer = AnthropicLanguageRecognizer(client)  # type: ignore[arg-type]

    result = await recognizer.recognize("Hay una fuga de agua.")

    assert result.language_code is LanguageCode.SPANISH


async def test_recognizer_maps_invalid_provider_output_to_undetermined() -> None:
    client = FakeClient("Spanish")
    recognizer = AnthropicLanguageRecognizer(client)  # type: ignore[arg-type]

    result = await recognizer.recognize("Ambiguous description")

    assert result.language_code is LanguageCode.UNDETERMINED


async def test_recognizer_skips_provider_for_blank_description() -> None:
    client = FakeClient("es")
    recognizer = AnthropicLanguageRecognizer(client)  # type: ignore[arg-type]

    result = await recognizer.recognize("   ")

    assert result.language_code is LanguageCode.UNDETERMINED
    assert client.messages.calls == 0


async def test_recognizer_disables_thinking() -> None:
    client = FakeClient("es")
    await AnthropicLanguageRecognizer(client).recognize("Hay una fuga.")  # type: ignore[arg-type]

    assert client.messages.last_kwargs["thinking"] == {"type": "disabled"}
