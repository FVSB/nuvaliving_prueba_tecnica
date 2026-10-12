"""Deterministic guards around the LLM evidence: whole days, bare hours, literal ranges."""

import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from maintenance_agent.application.conversation import MessageClass
from maintenance_agent.domain.date_validation import DateErrorCode
from maintenance_agent.domain.negotiation import ParticipantRole
from maintenance_agent.infrastructure.anthropic_conversation import (
    AnthropicConversationHandler,
    _availability_tool_results,
)
from maintenance_agent.prompts.compose_message import build_composition_prompt
from maintenance_agent.prompts.interpret_availability import build_availability_prompt
from maintenance_agent.prompts.slot_reply import (
    build_slot_compose_prompt,
    build_slot_validate_prompt,
)

ZONE = "Europe/Madrid"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=ZoneInfo(ZONE))


def output(**overrides) -> str:
    base = {
        "intervals": [],
        "suggested_intervals": [],
        "complete": False,
        "clarification_required": False,
        "date_confirmation_required": False,
        "weekday_is_today": False,
        "clarification": "",
        "classification": "unclassified",
        "date_from": "",
        "date_to": "",
        "part_of_day": "none",
        "ambiguity_reason": "other",
        "mentioned_dates": [],
    }
    return json.dumps({**base, **overrides})


def window(start: str, end: str) -> dict:
    return {"start": start, "end": end, "claimed_weekday": ""}


class SequenceClient:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.messages = self

    async def create(self, **kwargs):
        text = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


async def interpret(text: str, *responses: str):
    client = SequenceClient(*responses)
    result = await AnthropicConversationHandler(client).interpret_availability(
        text, ParticipantRole.TENANT, NOW, ZONE
    )
    return result, client


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["el viernes", "next week on Friday", "el 16"])
async def test_day_without_time_never_becomes_a_whole_day_interval(text) -> None:
    whole_day = output(
        intervals=[window("2026-10-16T00:00:00+02:00", "2026-10-16T23:59:00+02:00")],
        complete=True,
        classification="explicit_intervals",
    )
    result, _ = await interpret(text, whole_day)
    assert result.intervals == ()
    assert result.invalid_reason is None
    assert result.classification is MessageClass.VAGUE_DATE_REQUEST
    assert result.clarification_required is True
    assert (result.date_from, result.date_to) == ("2026-10-16", "2026-10-16")


@pytest.mark.asyncio
async def test_whole_day_is_kept_when_the_text_asks_for_it() -> None:
    whole_day = output(
        intervals=[window("2026-10-16T00:00:00+02:00", "2026-10-16T23:59:00+02:00")],
        complete=True,
        classification="explicit_intervals",
    )
    result, _ = await interpret("el 16 todo el día", whole_day)
    assert result.intervals == ()
    assert result.invalid_reason is not None
    assert result.invalid_reason.code is DateErrorCode.OUTSIDE_VISIT_HOURS


@pytest.mark.asyncio
async def test_short_early_interval_is_not_a_whole_day() -> None:
    early = output(
        intervals=[window("2026-10-16T00:00:00+02:00", "2026-10-16T03:00:00+02:00")],
        complete=True,
        classification="explicit_intervals",
    )
    result, _ = await interpret("el 16 de 00:30 a 03:00", early)
    assert result.invalid_reason is not None  # rejected by hours, not reinterpreted as vague


def vague(day: str = "2026-10-16", **overrides) -> str:
    return output(
        classification="vague_date_request",
        clarification_required=True,
        clarification="AM or PM?",
        date_from=day,
        date_to=day,
        ambiguity_reason="ambiguous_am_pm",
        **overrides,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "start"),
    [
        ("viernes a las 10", "2026-10-16T10:00:00+02:00"),
        ("el viernes a las 3", "2026-10-16T15:00:00+02:00"),
        ("Friday at 9", "2026-10-16T09:00:00+02:00"),
    ],
)
async def test_bare_hour_is_settled_by_the_visit_hours(text, start) -> None:
    result, _ = await interpret(text, vague())
    assert result.intervals[0].start == datetime.fromisoformat(start)
    assert (result.intervals[0].end - result.intervals[0].start).total_seconds() == 7200
    assert result.classification is MessageClass.EXPLICIT_INTERVALS
    assert result.clarification_required is False and result.invalid_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text", ["viernes a las 7", "viernes a las 10:30", "viernes a las 10 de la noche", "around 3"]
)
async def test_bare_hour_stays_vague_when_the_visit_hours_do_not_settle_it(text) -> None:
    day = "" if text == "around 3" else "2026-10-16"
    result, _ = await interpret(text, vague(day))
    assert result.intervals == ()
    assert result.classification is MessageClass.VAGUE_DATE_REQUEST


@pytest.mark.asyncio
async def test_bare_hour_in_the_past_today_is_rejected_by_validation() -> None:
    result, _ = await interpret("hoy a las 10", vague("2026-10-12"))
    assert result.invalid_reason is not None
    assert result.invalid_reason.code is DateErrorCode.IN_THE_PAST


@pytest.mark.asyncio
async def test_empty_intervals_for_a_literal_range_are_retried_then_rescued() -> None:
    empty = output(classification="explicit_intervals", complete=False)
    result, client = await interpret("Puedo el 2026-10-13 de 10:00 a 12:00.", empty, empty, empty)
    assert client.calls == 3
    assert len(result.intervals) == 1
    interval = result.intervals[0]
    assert interval.start.astimezone(ZoneInfo(ZONE)).isoformat() == "2026-10-13T10:00:00+02:00"
    assert interval.end.astimezone(ZoneInfo(ZONE)).isoformat() == "2026-10-13T12:00:00+02:00"
    assert result.complete is True and result.clarification_required is False


@pytest.mark.asyncio
async def test_retry_stops_as_soon_as_the_model_returns_the_interval() -> None:
    empty = output(classification="explicit_intervals")
    good = output(
        classification="explicit_intervals",
        complete=True,
        intervals=[window("2026-10-13T10:00:00+02:00", "2026-10-13T12:00:00+02:00")],
    )
    result, client = await interpret("Puedo el 2026-10-13 de 10:00 a 12:00.", empty, good)
    assert client.calls == 2 and len(result.intervals) == 1


@pytest.mark.asyncio
async def test_rescued_range_goes_through_validation() -> None:
    empty = output(classification="explicit_intervals")
    result, _ = await interpret("el 2026-10-13 de 03:00 a 05:00", empty)
    assert result.intervals == ()
    assert result.invalid_reason is not None
    assert result.invalid_reason.code is DateErrorCode.OUTSIDE_VISIT_HOURS


@pytest.mark.asyncio
async def test_rescue_is_skipped_when_the_model_asked_for_clarification() -> None:
    asked = output(clarification_required=True, clarification="Which day?")
    result, _ = await interpret("2026-10-13 de 10:00 a 12:00", asked)
    assert result.intervals == ()


@pytest.mark.asyncio
async def test_rescue_is_skipped_for_ambiguous_text() -> None:
    empty = output()
    result, _ = await interpret("2026-10-13 o 2026-10-14, de 10:00 a 12:00", empty)
    assert result.intervals == ()


def test_resolve_bare_hour_tool_result_follows_the_visit_hours() -> None:
    def call(hour):
        block = SimpleNamespace(
            type="tool_use", name="resolve_bare_hour", input={"hour": hour}, id="t"
        )
        return json.loads(_availability_tool_results([block], NOW, ZONE)[0]["content"])

    assert call(10) == {"hour_24": 10}
    assert call(3) == {"hour_24": 15}
    assert call(7) == {"hour_24": None}


def test_availability_prompt_orders_bare_hours_and_forbids_whole_days() -> None:
    prompt = build_availability_prompt("viernes a las 10", ParticipantRole.TENANT, NOW, ZONE)
    assert "resolve_bare_hour" in prompt
    assert "never a whole-day interval" in prompt


def test_compose_prompt_pins_dates_to_the_facts() -> None:
    prompt = build_composition_prompt(
        "ask", "es", {"today": "2026-10-12", "day": "martes 2026-10-13"}
    )
    assert "`today`" in prompt
    assert "Copy every date" in prompt
    assert "Never invent dates" in prompt
    assert "never reformat a date, change or add a weekday" in prompt
    assert "absent" in prompt  # works without `today`
    assert build_composition_prompt("ask", "es", {"x": "y"}).endswith('Facts: {"x": "y"}')


def test_slot_prompts_do_not_demand_a_single_short_sentence() -> None:
    compose = build_slot_compose_prompt("es", "| t |", "w", "")
    validate = build_slot_validate_prompt("reply", "| t |", "w", "es")
    for prompt in (compose, validate):
        assert "one short sentence" not in prompt
    assert "do not reject for length" in validate
    assert "invent" in compose and "promise" in compose
