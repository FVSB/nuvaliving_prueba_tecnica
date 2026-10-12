from types import SimpleNamespace

import pytest

from maintenance_agent.infrastructure.anthropic_conversation import AnthropicConversationHandler


class _Messages:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.responses.pop(0))])


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

    call = SimpleNamespace(
        type="tool_use", id="s1", name="read_skill", input={"name": "relative-date-phrases"}
    )
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

    client = SimpleNamespace(messages=_TruncatedMessages(['{"intro":"Hola']))
    with pytest.raises(LlmOutputError, match="truncated at max_tokens"):
        await AnthropicConversationHandler(client).compose_slot_reply("Spanish", FACTS)


@pytest.mark.asyncio
async def test_compose_without_text_block_names_block_types() -> None:
    from maintenance_agent.infrastructure.anthropic_conversation import LlmOutputError

    class _NoText(_Messages):
        async def create(self, **kwargs):
            return SimpleNamespace(
                stop_reason="end_turn", content=[SimpleNamespace(type="thinking")]
            )

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


def _availability_json(start: str, end: str) -> str:
    return (
        '{"intervals":[{"start":"%s","end":"%s"}],"suggested_intervals":[],'
        '"complete":true,"clarification_required":false,"date_confirmation_required":false,'
        '"weekday_is_today":false,"clarification":"","classification":"explicit_intervals"}'
        % (start, end)
    )


async def _interpret(client, text: str = "x"):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from maintenance_agent.domain.negotiation import ParticipantRole

    now = datetime(2026, 10, 12, 12, tzinfo=ZoneInfo("Europe/Madrid"))
    return await AnthropicConversationHandler(client).interpret_availability(
        text, ParticipantRole.TENANT, now, "Europe/Madrid"
    )


@pytest.mark.asyncio
async def test_every_model_call_disables_thinking() -> None:
    client = _Client(
        _availability_json("2026-10-13T10:00:00+02:00", "2026-10-13T12:00:00+02:00"),
        '{"intro":"a","ask":"b"}',
        '{"valid":true,"feedback":""}',
        "Hola",
    )
    handler = AnthropicConversationHandler(client)
    await _interpret(client)
    await handler.compose_slot_reply("Spanish", FACTS)
    await handler.validate_slot_reply("draft", FACTS)
    await handler.compose("intent", "Spanish", {})
    assert len(client.messages.calls) == 4
    assert all(call["thinking"] == {"type": "disabled"} for call in client.messages.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("start", "end", "code"),
    [
        ("2026-10-13T03:00:00+02:00", "2026-10-13T05:00:00+02:00", "outside_visit_hours"),
        ("2062-10-20T10:00:00+02:00", "2062-10-20T12:00:00+02:00", "too_far_ahead"),
        ("2026-10-11T10:00:00+02:00", "2026-10-11T12:00:00+02:00", "in_the_past"),
        ("2026-02-30T10:00:00+01:00", "2026-02-30T12:00:00+01:00", "not_a_calendar_date"),
        ("2026-10-13T25:00:00+02:00", "2026-10-13T27:00:00+02:00", "invalid_time"),
    ],
)
async def test_invalid_interval_is_rejected_with_reason(start: str, end: str, code: str) -> None:
    result = await _interpret(_Client(_availability_json(start, end)))
    assert result.invalid_reason is not None and result.invalid_reason.code.value == code
    assert result.intervals == ()
    assert result.complete is False and result.clarification_required is True


@pytest.mark.asyncio
async def test_valid_interval_has_no_invalid_reason() -> None:
    result = await _interpret(
        _Client(_availability_json("2026-10-13T10:00:00+02:00", "2026-10-13T12:00:00+02:00"))
    )
    assert result.invalid_reason is None and len(result.intervals) == 1


@pytest.mark.asyncio
async def test_broken_json_is_retried_once_then_falls_back() -> None:
    client = _Client("nope", "still nope")
    result = await _interpret(client)
    assert len(client.messages.calls) == 2
    assert result.intervals == () and result.clarification_required and not result.complete
    assert result.invalid_reason is None

    good = _Client(
        "nope", _availability_json("2026-10-13T10:00:00+02:00", "2026-10-13T12:00:00+02:00")
    )
    assert len((await _interpret(good)).intervals) == 1


@pytest.mark.asyncio
async def test_validate_date_tool_reports_weekday_mismatch() -> None:
    import json
    from datetime import datetime

    from maintenance_agent.infrastructure.anthropic_conversation import (
        _availability_tool_results,
    )

    call = SimpleNamespace(
        type="tool_use",
        id="v1",
        name="validate_date",
        input={"date": "2026-10-15", "time": "10:00", "claimed_weekday": "lunes"},
    )
    (result,) = _availability_tool_results([call], datetime(2026, 10, 12, 12), "Europe/Madrid")
    payload = json.loads(result["content"])
    assert payload["valid"] is False and payload["code"] == "weekday_mismatch"
    assert payload["actual_weekday"] == "Thursday"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mention", "code"),
    [
        ('{"day":31,"month":4,"year":2027,"hour":10,"minute":0}', "not_a_calendar_date"),
        ('{"day":13,"month":10,"year":2026,"hour":25,"minute":0}', "invalid_time"),
        ('{"day":15,"month":10,"year":2026,"hour":10,"weekday":"Monday"}', "weekday_mismatch"),
        ('{"day":1,"month":10,"year":2026,"hour":10}', "in_the_past"),
    ],
)
async def test_mentioned_dates_reject_without_intervals_or_tool_call(mention, code) -> None:
    body = (
        '{"intervals":[],"suggested_intervals":[],"complete":true,"clarification_required":false,'
        '"date_confirmation_required":false,"weekday_is_today":false,"clarification":"",'
        '"mentioned_dates":[{"text":"x","day":null,"month":null,"year":null,"hour":null,'
        '"minute":null,"weekday":"","relative":false}]}'
    ).replace(
        '{"text":"x","day":null,"month":null,"year":null,"hour":null,'
        '"minute":null,"weekday":"","relative":false}',
        '{"text":"x",' + mention[1:],
    )
    result = await _interpret(_Client(body))
    assert result.invalid_reason is not None and result.invalid_reason.code.value == code
    assert not result.complete and result.clarification_required and not result.intervals


@pytest.mark.asyncio
async def test_missing_mentioned_dates_field_still_parses() -> None:
    result = await _interpret(
        _Client(_availability_json("2026-10-13T10:00:00+02:00", "2026-10-13T12:00:00+02:00"))
    )
    assert result.invalid_reason is None and len(result.intervals) == 1
