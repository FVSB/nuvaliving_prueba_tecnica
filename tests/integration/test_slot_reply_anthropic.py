from types import SimpleNamespace

import pytest

from maintenance_agent.infrastructure.anthropic_conversation import AnthropicConversationHandler


class _Messages:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.responses.pop(0))]
        )


class _Client:
    def __init__(self, *responses: str) -> None:
        self.messages = _Messages(list(responses))


FACTS = {"table": "| T |", "next_slot_line": "SLOT-1", "feedback": "", "language": "Spanish"}


@pytest.mark.asyncio
async def test_compose_slot_reply_returns_prose_only_with_schema() -> None:
    client = _Client('{"intro":" Hola ","ask":" Elija "}')
    intro, ask = await AnthropicConversationHandler(client).compose_slot_reply("Spanish", FACTS)
    assert (intro, ask) == ("Hola", "Elija")
    call = client.messages.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "| T |" in call["messages"][0]["content"]


@pytest.mark.asyncio
async def test_validator_maps_verdict_and_feedback() -> None:
    client = _Client('{"valid":false,"feedback":"Wrong language"}')
    verdict = await AnthropicConversationHandler(client).validate_slot_reply("draft", FACTS)
    assert verdict.valid is False and verdict.feedback == "Wrong language"


@pytest.mark.asyncio
async def test_malformed_validator_output_is_invalid_never_valid() -> None:
    verdict = await AnthropicConversationHandler(_Client("nope")).validate_slot_reply("d", FACTS)
    assert verdict.valid is False and verdict.feedback


@pytest.mark.asyncio
async def test_classification_is_parsed_and_unknown_becomes_unclassified() -> None:
    from datetime import datetime

    from maintenance_agent.application.conversation import MessageClass
    from maintenance_agent.domain.negotiation import ParticipantRole

    base = (
        '{"intervals":[],"suggested_intervals":[],"complete":false,'
        '"clarification_required":true,"date_confirmation_required":false,'
        '"weekday_is_today":false,"clarification":"","classification":"%s"}'
    )
    for raw, expected in (
        ("vague_date_request", MessageClass.VAGUE_DATE_REQUEST),
        ("bogus", MessageClass.UNCLASSIFIED),
    ):
        handler = AnthropicConversationHandler(_Client(base % raw))
        result = await handler.interpret_availability(
            "x", ParticipantRole.TENANT, datetime(2026, 10, 12, 12), "Europe/Madrid"
        )
        assert result.classification is expected


@pytest.mark.asyncio
async def test_interpreter_resolves_next_week_start_through_tool_loop() -> None:
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from maintenance_agent.domain.negotiation import ParticipantRole

    final = (
        '{"intervals":[],"suggested_intervals":[],"complete":false,'
        '"clarification_required":true,"date_confirmation_required":false,'
        '"weekday_is_today":false,"clarification":"","classification":"vague_date_request",'
        '"date_from":"2026-10-19","date_to":"2026-10-20","part_of_day":"none",'
        '"ambiguity_reason":"unspecified_time"}'
    )

    class _ToolThenFinal(_Messages):
        async def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                call = SimpleNamespace(
                    type="tool_use",
                    id="t1",
                    name="resolve_relative_range",
                    input={"kind": "next_week"},
                )
                return SimpleNamespace(content=[call])
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=final)])

    client = SimpleNamespace(messages=_ToolThenFinal([]))
    now = datetime(2026, 10, 12, 8, tzinfo=ZoneInfo("Europe/Madrid"))
    result = await AnthropicConversationHandler(client).interpret_availability(
        "la semana próxima a inicio de semana", ParticipantRole.TENANT, now, "Europe/Madrid"
    )
    tool_result = client.messages.calls[1]["messages"][-1]["content"][0]["content"]
    assert json.loads(tool_result)["date_from"] == "2026-10-19"
    assert json.loads(tool_result)["days"][0]["weekday"] == "Monday"
    assert (result.date_from, result.date_to) == ("2026-10-19", "2026-10-20")
    assert "resolve_relative_range" in [t["name"] for t in client.messages.calls[0]["tools"]]


@pytest.mark.asyncio
async def test_read_skill_tool_returns_body_on_demand() -> None:
    import json
    from datetime import datetime

    from maintenance_agent.infrastructure.anthropic_conversation import (
        _availability_tool_results,
    )

    call = SimpleNamespace(type="tool_use", id="s1", name="read_skill",
                           input={"name": "relative-date-phrases"})
    (result,) = _availability_tool_results([call], datetime(2026, 10, 12, 8), "Europe/Madrid")
    assert "Monday and Tuesday" in json.loads(result["content"])["skill"]


class _TruncatedMessages(_Messages):
    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason="max_tokens",
            content=[SimpleNamespace(type="text", text=self.responses.pop(0))],
        )


@pytest.mark.asyncio
async def test_truncated_compose_reply_reports_stop_reason() -> None:
    from maintenance_agent.infrastructure.anthropic_conversation import LlmOutputError

    client = SimpleNamespace(messages=_TruncatedMessages(['{"intro":"Hola'] ))
    with pytest.raises(LlmOutputError, match="truncated at max_tokens"):
        await AnthropicConversationHandler(client).compose_slot_reply("Spanish", FACTS)


@pytest.mark.asyncio
async def test_compose_without_text_block_names_block_types() -> None:
    from maintenance_agent.infrastructure.anthropic_conversation import LlmOutputError

    class _NoText(_Messages):
        async def create(self, **kwargs):
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="thinking")])

    client = SimpleNamespace(messages=_NoText([]))
    with pytest.raises(LlmOutputError, match="blocks=\\['thinking'\\]"):
        await AnthropicConversationHandler(client).compose_slot_reply("Spanish", FACTS)


@pytest.mark.asyncio
async def test_unreadable_validator_verdict_keeps_diagnostic_out_of_feedback() -> None:
    client = SimpleNamespace(messages=_TruncatedMessages(['{"valid":']))
    verdict = await AnthropicConversationHandler(client).validate_slot_reply("d", FACTS)
    assert verdict.valid is False
    assert verdict.feedback == "The validator returned an unreadable verdict."
    assert "truncated at max_tokens" in (verdict.diagnostic or "")
