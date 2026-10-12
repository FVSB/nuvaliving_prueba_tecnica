from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from maintenance_agent import bootstrap
from maintenance_agent.config import Settings
from maintenance_agent.domain.negotiation import ParticipantRole
from maintenance_agent.infrastructure.anthropic_conversation import AnthropicConversationHandler
from maintenance_agent.infrastructure.anthropic_language_recognizer import (
    AnthropicLanguageRecognizer,
)


def test_settings_default_and_custom_anthropic_models() -> None:
    defaults = Settings(_env_file=None)
    custom = Settings(
        _env_file=None,
        anthropic_language_model="language-model-x",
        anthropic_conversation_model="conversation-model-y",
    )

    assert defaults.anthropic_language_model == "claude-haiku-5-5"
    assert defaults.anthropic_conversation_model == "claude-haiku-5-5"
    assert custom.anthropic_language_model == "language-model-x"
    assert custom.anthropic_conversation_model == "conversation-model-y"


@pytest.mark.parametrize("field", ["anthropic_language_model", "anthropic_conversation_model"])
def test_settings_reject_empty_anthropic_model(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: "  "})


class FakeMessages:
    def __init__(self, response_text: str = '{"intervals":[]}') -> None:
        self.models: list[str] = []
        self.calls: list[dict[str, object]] = []
        self.response_text = response_text
        self.responses: list[list[SimpleNamespace]] = []

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.models.append(str(kwargs["model"]))
        self.calls.append(kwargs)
        content = (
            self.responses.pop(0)
            if self.responses
            else [SimpleNamespace(type="text", text=self.response_text)]
        )
        return SimpleNamespace(content=content)


class FakeClient:
    def __init__(self) -> None:
        self.messages = FakeMessages()


async def test_conversation_handler_sends_configured_model() -> None:
    client = FakeClient()
    handler = AnthropicConversationHandler(client, model="custom-conversation")  # type: ignore[arg-type]

    await handler.compose("greeting", "en", {})

    assert client.messages.models == ["custom-conversation"]


async def test_relative_weekday_uses_anthropic_structured_availability_output() -> None:
    response = (
        '{"intervals":[],"suggested_intervals":['
        '{"start":"2026-10-19T12:00:00+02:00","end":"2026-10-19T14:00:00+02:00"}],'
        '"complete":false,"clarification_required":false,'
        '"date_confirmation_required":true,"weekday_is_today":true,"clarification":""}'
    )
    client = FakeClient()
    client.messages.response_text = response
    handler = AnthropicConversationHandler(client, model="custom-conversation")  # type: ignore[arg-type]
    reference = datetime(2026, 10, 12, 10, tzinfo=ZoneInfo("Europe/Madrid"))

    result = await handler.interpret_availability(
        "lunes de 12-14", ParticipantRole.TENANT, reference, "Europe/Madrid"
    )

    call = client.messages.calls[0]
    output_config = call["output_config"]
    assert output_config["format"]["type"] == "json_schema"
    schema = output_config["format"]["schema"]
    assert "suggested_intervals" in schema["properties"]
    prompt = call["messages"][0]["content"]
    assert reference.isoformat() in prompt
    assert "Europe/Madrid" in prompt
    assert result.date_confirmation_required is True
    assert result.intervals == ()
    assert result.suggested_intervals[0].start.isoformat() == "2026-10-19T10:00:00+00:00"


async def test_relative_weekday_can_call_injected_local_calendar_tool() -> None:
    response = (
        '{"intervals":[],"suggested_intervals":['
        '{"start":"2026-10-19T12:00:00+02:00","end":"2026-10-19T14:00:00+02:00"}],'
        '"complete":false,"clarification_required":false,'
        '"date_confirmation_required":true,"weekday_is_today":false,"clarification":""}'
    )
    client = FakeClient()
    client.messages.response_text = response
    client.messages.responses = [
        [
            SimpleNamespace(
                type="tool_use",
                id="tool-call-1",
                name="get_local_calendar_context",
                input={},
            )
        ]
    ]
    handler = AnthropicConversationHandler(client, model="injected-model")  # type: ignore[arg-type]
    reference = datetime(2026, 10, 12, 10, tzinfo=ZoneInfo("Europe/Madrid"))

    result = await handler.interpret_availability(
        "el próximo lunes", ParticipantRole.TENANT, reference, "Europe/Madrid"
    )

    first, second = client.messages.calls
    assert first["model"] == second["model"] == "injected-model"
    assert first["tools"][0]["name"] == "get_local_calendar_context"
    assert first["tools"][0]["strict"] is True
    assert first["tool_choice"] == {"type": "auto"}
    tool_result = second["messages"][2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "tool-call-1"
    assert '"date": "2026-10-12"' in tool_result["content"]
    assert '"weekday": "Monday"' in tool_result["content"]
    assert result.suggested_intervals[0].start.isoformat() == "2026-10-19T10:00:00+00:00"


async def test_language_recognizer_sends_configured_model() -> None:
    client = FakeClient()
    recognizer = AnthropicLanguageRecognizer(client, model="custom-language")  # type: ignore[arg-type]

    await recognizer.recognize("A plumbing issue")

    assert client.messages.models == ["custom-language"]


def test_bootstrap_injects_configured_models_and_snapshots_them(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path

    from pydantic import SecretStr

    traces_dir = Path(str(tmp_path)) / "traces"
    settings = Settings(
        _env_file=None,
        anthropic_api_key=SecretStr("test-key"),
        anthropic_language_model="language-config",
        anthropic_conversation_model="conversation-config",
        traces_dir=traces_dir,
    )
    fake_client = FakeClient()
    monkeypatch.setattr(bootstrap, "Settings", lambda: settings)
    monkeypatch.setattr(bootstrap, "AsyncAnthropic", lambda **_: fake_client)

    container = bootstrap.build_container()
    recognizer = container.language_recognizer()
    conversation = container.conversation_handler()
    snapshot = bootstrap._effective_snapshot(settings, container.run_context())

    assert recognizer._model == "language-config"
    assert conversation._model == "conversation-config"
    assert snapshot["anthropic_language_model"] == "language-config"
    assert snapshot["anthropic_conversation_model"] == "conversation-config"
    assert "anthropic_api_key" not in snapshot
