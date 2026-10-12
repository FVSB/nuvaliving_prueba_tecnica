"""Anthropic-backed typed interpretation and language-scoped composition."""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ConfigDict, ValidationError

from maintenance_agent.application.conversation import (
    AvailabilityInterpretation,
    DecisionInterpretation,
    AmbiguityReason,
    MessageClass,
    PartOfDay,
    ValidationVerdict,
)
from maintenance_agent.domain.calendar_ranges import KINDS, resolve_range
from maintenance_agent.domain.decisions import interpret_explicit_decision
from maintenance_agent.domain.negotiation import ParticipantRole, TimeInterval
from maintenance_agent.domain.scheduling import visit_interval_from_start
from maintenance_agent.prompts.compose_message import build_composition_prompt
from maintenance_agent.prompts.interpret_availability import build_availability_prompt
from maintenance_agent.skills import load_skills, read_skill
from maintenance_agent.prompts.slot_reply import (
    build_slot_compose_prompt,
    build_slot_validate_prompt,
)


class _WindowOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str
    end: str

    def to_interval(self) -> TimeInterval:
        return TimeInterval(datetime.fromisoformat(self.start), datetime.fromisoformat(self.end))


class _AvailabilityOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intervals: list[_WindowOutput]
    suggested_intervals: list[_WindowOutput]
    complete: bool
    clarification_required: bool
    date_confirmation_required: bool
    weekday_is_today: bool
    clarification: str
    classification: str = "unclassified"
    date_from: str = ""
    date_to: str = ""
    part_of_day: str = "none"
    ambiguity_reason: str = "other"


class _SlotReplyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intro: str
    ask: str


class _ValidationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    feedback: str = ""


class AnthropicConversationHandler:
    def __init__(self, client: AsyncAnthropic, model: str = "claude-haiku-5-5") -> None:
        self._client = client
        self._model = model

    async def _text(self, prompt: str, max_tokens: int = 300) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        result = next(
            (block.text for block in response.content if getattr(block, "type", None) == "text"),
            "",
        )
        return result.strip()

    async def interpret_availability(
        self,
        text: str,
        role: ParticipantRole,
        reference_time: datetime,
        timezone_name: str,
    ) -> AvailabilityInterpretation:
        try:
            prompt = build_availability_prompt(text, role, reference_time, timezone_name)
            messages: list[dict[str, object]] = [{"role": "user", "content": prompt}]
            response = None
            for _ in range(4):
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=600,
                    messages=messages,
                    tools=[
                        _calendar_tool(),
                        _add_two_hour_end_tool(),
                        _resolve_range_tool(),
                        _read_skill_tool(),
                    ],
                    tool_choice={"type": "auto"},
                    output_config={
                        "format": {
                            "type": "json_schema",
                            "schema": _availability_schema(),
                        }
                    },
                )
                tool_calls = [
                    block
                    for block in response.content
                    if getattr(block, "type", None) == "tool_use"
                ]
                if not tool_calls:
                    break
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": _availability_tool_results(
                            tool_calls, reference_time, timezone_name
                        ),
                    }
                )
            raw = next(
                (
                    block.text
                    for block in response.content
                    if getattr(block, "type", None) == "text"
                ),
                "",
            )
            result = _AvailabilityOutput.model_validate_json(raw)
            return AvailabilityInterpretation(
                tuple(window.to_interval() for window in result.intervals),
                result.complete,
                result.clarification_required,
                tuple(window.to_interval() for window in result.suggested_intervals),
                result.date_confirmation_required,
                result.clarification or None,
                result.weekday_is_today,
                _message_class(result.classification),
                result.date_from or None,
                result.date_to or None,
                _enum_or(PartOfDay, result.part_of_day, PartOfDay.NONE),
                _enum_or(AmbiguityReason, result.ambiguity_reason, AmbiguityReason.OTHER),
            )
        except (TypeError, ValueError):
            return AvailabilityInterpretation((), False, True)

    async def interpret_decision(self, text: str, role: ParticipantRole) -> DecisionInterpretation:
        """Read an explicit yes/no only; anything else becomes a clarification."""
        decision = interpret_explicit_decision(text)
        return DecisionInterpretation(decision, decision is None)

    async def compose(self, intent: str, language: str, facts: dict[str, str]) -> str:
        return await self._text(build_composition_prompt(intent, language, facts), 300)

    async def compose_slot_reply(
        self, language: str, facts: dict[str, str]
    ) -> tuple[str, str]:
        """Return LLM intro/ask prose; the deterministic table is injected by the caller."""
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": build_slot_compose_prompt(
                        language,
                        facts.get("table", ""),
                        facts.get("window", ""),
                        facts.get("feedback", ""),
                    ),
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": _SLOT_REPLY_SCHEMA}},
        )
        output = _structured_output(response, _SlotReplyOutput, "compose_slot_reply")
        return output.intro.strip(), output.ask.strip()

    async def validate_slot_reply(
        self, reply: str, facts: dict[str, str]
    ) -> ValidationVerdict:
        """Judge the prose around the table; any malformed verdict is invalid."""
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": build_slot_validate_prompt(
                            reply,
                            facts.get("table", ""),
                            facts.get("window", ""),
                            facts.get("language", ""),
                        ),
                    }
                ],
                output_config={
                    "format": {"type": "json_schema", "schema": _VALIDATION_SCHEMA}
                },
            )
            verdict = _structured_output(response, _ValidationOutput, "validate_slot_reply")
        except (TypeError, ValueError) as error:
            return ValidationVerdict(
                False, "The validator returned an unreadable verdict.", diagnostic=str(error)
            )
        return ValidationVerdict(verdict.valid, verdict.feedback.strip() or None)


class LlmOutputError(ValueError):
    """The model reply was not the requested structured output; the message names why."""


def _first_text(response) -> str:
    return next(
        (block.text for block in response.content if getattr(block, "type", None) == "text"),
        "",
    )


def _structured_output[ModelT: BaseModel](response, model_type: type[ModelT], label: str) -> ModelT:
    """Parse a structured reply, keeping stop_reason, block types and a text excerpt on failure."""
    text = _first_text(response)
    stop_reason = getattr(response, "stop_reason", None)
    blocks = [getattr(block, "type", None) for block in response.content]
    context = f"{label}: stop_reason={stop_reason} blocks={blocks} text={text[:200]!r}"
    if stop_reason == "max_tokens":
        raise LlmOutputError(f"truncated at max_tokens; {context}")
    try:
        return model_type.model_validate_json(text)
    except ValidationError as error:
        problems = [f"{'.'.join(map(str, e['loc']))}:{e['type']}" for e in error.errors()]
        raise LlmOutputError(f"schema mismatch {problems}; {context}") from error


def _enum_or(enum_type, value: str, default):
    try:
        return enum_type(value)
    except ValueError:
        return default


def _message_class(value: str) -> MessageClass:
    try:
        return MessageClass(value)
    except ValueError:
        return MessageClass.UNCLASSIFIED


_SLOT_REPLY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"intro": {"type": "string"}, "ask": {"type": "string"}},
    "required": ["intro", "ask"],
    "additionalProperties": False,
}

_VALIDATION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"valid": {"type": "boolean"}, "feedback": {"type": "string"}},
    "required": ["valid", "feedback"],
    "additionalProperties": False,
}


def _availability_schema() -> dict[str, object]:
    """Return the constrained Anthropic JSON schema for availability interpretation."""
    window = {
        "type": "object",
        "properties": {"start": {"type": "string"}, "end": {"type": "string"}},
        "required": ["start", "end"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "intervals": {"type": "array", "items": window},
            "suggested_intervals": {"type": "array", "items": window},
            "complete": {"type": "boolean"},
            "clarification_required": {"type": "boolean"},
            "date_confirmation_required": {"type": "boolean"},
            "weekday_is_today": {"type": "boolean"},
            "clarification": {"type": "string"},
            "classification": {
                "type": "string",
                "enum": [member.value for member in MessageClass],
            },
            "date_from": {"type": "string"},
            "date_to": {"type": "string"},
            "part_of_day": {"type": "string", "enum": [m.value for m in PartOfDay]},
            "ambiguity_reason": {
                "type": "string",
                "enum": [m.value for m in AmbiguityReason],
            },
        },
        "required": [
            "intervals",
            "suggested_intervals",
            "complete",
            "clarification_required",
            "date_confirmation_required",
            "weekday_is_today",
            "clarification",
            "classification",
            "date_from",
            "date_to",
            "part_of_day",
            "ambiguity_reason",
        ],
        "additionalProperties": False,
    }


def _calendar_tool() -> dict[str, object]:
    return {
        "name": "get_local_calendar_context",
        "description": (
            "Get the authoritative local date, weekday, and upcoming dates for the "
            "configured timezone. Call it to resolve relative weekdays or dates."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    }


def _add_two_hour_end_tool() -> dict[str, object]:
    return {
        "name": "add_two_hour_end",
        "description": (
            "For a tenant availability statement with a date and start time but no end time, "
            "return the interval ending exactly two elapsed hours after that start."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"start": {"type": "string"}},
            "required": ["start"],
            "additionalProperties": False,
        },
    }


def _resolve_range_tool() -> dict[str, object]:
    return {
        "name": "resolve_relative_range",
        "description": (
            "Resolve a relative period (today, tomorrow, day_after_tomorrow, this_week, "
            "next_week, weekend) into an inclusive local date range with each day and weekday. "
            "Past days are never returned. Always use it instead of computing dates yourself."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": list(KINDS)}},
            "required": ["kind"],
            "additionalProperties": False,
        },
    }


def _read_skill_tool() -> dict[str, object]:
    return {
        "name": "read_skill",
        "description": (
            "Read the full text of a skill from the catalogue in the prompt. Call it only when "
            "its description says it applies to the message; skip it otherwise."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "enum": list(load_skills())}},
            "required": ["name"],
            "additionalProperties": False,
        },
    }


def _availability_tool_results(
    tool_calls: list[object], reference_time: datetime, timezone_name: str
) -> list[dict[str, str]]:
    results = []
    for block in tool_calls:
        name = getattr(block, "name", "")
        arguments = getattr(block, "input", {})
        if name == "get_local_calendar_context":
            result: dict[str, object] = _local_calendar_context(reference_time, timezone_name)
        elif name == "add_two_hour_end":
            try:
                start = datetime.fromisoformat(arguments["start"])
                interval = visit_interval_from_start(start, timezone_name)
                result = {"start": interval.start.isoformat(), "end": interval.end.isoformat()}
            except (KeyError, TypeError, ValueError) as error:
                result = {"error": f"invalid_start: {type(error).__name__}"}
        elif name == "resolve_relative_range":
            local_today = reference_time.astimezone(ZoneInfo(timezone_name)).date()
            resolved = resolve_range(local_today, str(arguments.get("kind")))
            result = (
                {
                    "date_from": resolved.date_from.isoformat(),
                    "date_to": resolved.date_to.isoformat(),
                    "days": [
                        {"date": day.isoformat(), "weekday": day.strftime("%A")}
                        for day in resolved.days()
                    ],
                }
                if resolved
                else {"error": "no_remaining_days_in_range"}
            )
        elif name == "read_skill":
            body = read_skill(str(arguments.get("name")))
            result = {"skill": body} if body else {"error": "unknown_skill"}
        else:
            result = {"error": "unsupported_tool"}
        results.append(
            {
                "type": "tool_result",
                "tool_use_id": getattr(block, "id", ""),
                "content": json.dumps(result, ensure_ascii=False),
            }
        )
    return results


def _local_calendar_context(reference_time: datetime, timezone_name: str) -> dict[str, object]:
    local_now = reference_time.astimezone(ZoneInfo(timezone_name))
    upcoming = [local_now.date() + timedelta(days=offset) for offset in range(32)]
    return {
        "timezone": timezone_name,
        "local_now": local_now.isoformat(),
        "today": {"date": local_now.date().isoformat(), "weekday": local_now.strftime("%A")},
        "upcoming_days": [
            {"date": date.isoformat(), "weekday": date.strftime("%A")} for date in upcoming
        ],
    }
