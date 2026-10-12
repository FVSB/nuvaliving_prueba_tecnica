"""Anthropic-backed typed interpretation and language-scoped composition."""

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ConfigDict, ValidationError

from maintenance_agent.application.conversation import (
    AmbiguityReason,
    AvailabilityInterpretation,
    DecisionInterpretation,
    MessageClass,
    PartOfDay,
)
from maintenance_agent.domain.calendar_ranges import KINDS, resolve_range
from maintenance_agent.domain.date_validation import (
    DateCheck,
    DateErrorCode,
    MentionedDate,
    check_timestamp_syntax,
    first_mention_problem,
    resolve_bare_hour,
    validate_date_text,
    validate_interval,
)
from maintenance_agent.domain.decisions import interpret_explicit_decision
from maintenance_agent.domain.negotiation import ParticipantRole, TimeInterval
from maintenance_agent.domain.scheduling import visit_interval_from_start
from maintenance_agent.infrastructure.trace_writer import TraceWriter
from maintenance_agent.prompts.compose_message import build_composition_prompt
from maintenance_agent.prompts.interpret_availability import build_availability_prompt
from maintenance_agent.prompts.slot_reply import (
    build_language_detect_prompt,
    build_slot_compose_prompt,
    build_translate_prompt,
)
from maintenance_agent.skills import load_skills, read_skill


class _WindowOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str
    end: str
    claimed_weekday: str = ""

    def syntax_problem(self) -> DateCheck | None:
        return check_timestamp_syntax(self.start) or check_timestamp_syntax(self.end)

    def to_interval(self) -> TimeInterval:
        return TimeInterval(datetime.fromisoformat(self.start), datetime.fromisoformat(self.end))


class _MentionedDateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""
    day: int | None = None
    month: int | None = None
    year: int | None = None
    hour: int | None = None
    minute: int | None = None
    weekday: str = ""
    relative: bool = False

    def to_mention(self) -> MentionedDate:
        return MentionedDate(**self.model_dump())


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
    mentioned_dates: list[_MentionedDateOutput] = []


class _SlotReplyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intro: str
    ask: str


class _LanguageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str


_ISO_DATE = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b")
_CLOCK = re.compile(r"\b\d{1,2}:\d{2}\b")


@dataclass(frozen=True, slots=True)
class _DateLimits:
    start_hour: int = 9
    end_hour: int = 19
    horizon_days: int = 7


class AnthropicConversationHandler:
    def __init__(
        self,
        client: AsyncAnthropic,
        model: str = "claude-haiku-5-5",
        *,
        start_hour: int = 9,
        end_hour: int = 19,
        horizon_days: int = 7,
        runtime_writer: TraceWriter | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._limits = _DateLimits(start_hour, end_hour, horizon_days)
        self._runtime_writer = runtime_writer
        self._skills = load_skills()
        if not self._skills and self._runtime_writer is not None:
            self._runtime_writer.write(
                event_type="skills_unavailable",
                detail={"action": "read_skill tool disabled; continuing without skills"},
            )

    async def _text(self, prompt: str, max_tokens: int = 300) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            thinking={"type": "disabled"},
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
        history: tuple[tuple[str, str], ...] = (),
    ) -> AvailabilityInterpretation:
        prompt = build_availability_prompt(text, role, reference_time, timezone_name, history)
        result = None
        failed_checks: list[DateCheck] = []
        broken = 0
        for _ in range(3):
            raw = await self._availability_json(
                prompt, reference_time, timezone_name, failed_checks
            )
            try:
                parsed = _AvailabilityOutput.model_validate_json(raw)
            except ValidationError:
                broken += 1
                if broken == 2:
                    break
                continue
            result = parsed
            if not (
                _claims_intervals_without_any(parsed)
                or _misses_obvious_interval(parsed, text)
                or self._lazy_explicit(parsed, reference_time, timezone_name)
            ):
                break
        if result is None:
            return AvailabilityInterpretation((), False, True)
        result = self._normalized(result, text, reference_time, timezone_name)
        rejection = first_mention_problem(
            [mention.to_mention() for mention in result.mentioned_dates],
            reference_time,
            timezone_name,
            start_hour=self._limits.start_hour,
            end_hour=self._limits.end_hour,
            horizon_days=self._limits.horizon_days,
        ) or self._rejection(result, reference_time, timezone_name)
        if rejection is None and not (result.intervals or result.suggested_intervals):
            rejection = (
                failed_checks[0]
                if failed_checks
                else self._literal_date_problem(text, reference_time, timezone_name)
            )
        if rejection is not None:
            return AvailabilityInterpretation((), False, True, invalid_reason=rejection)
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

    def _lazy_explicit(
        self, output: "_AvailabilityOutput", reference_time: datetime, timezone_name: str
    ) -> bool:
        """An explicit_intervals verdict with no interval and no date problem to explain it."""
        return (
            output.classification == MessageClass.EXPLICIT_INTERVALS
            and not output.intervals
            and not output.suggested_intervals
            and not output.clarification_required
            and first_mention_problem(
                [mention.to_mention() for mention in output.mentioned_dates],
                reference_time,
                timezone_name,
                start_hour=self._limits.start_hour,
                end_hour=self._limits.end_hour,
                horizon_days=self._limits.horizon_days,
            )
            is None
        )

    def _normalized(
        self, result: "_AvailabilityOutput", text: str, reference_time: datetime, timezone_name: str
    ) -> "_AvailabilityOutput":
        """Deterministic corrections to the model evidence, applied before any validation."""
        zone = ZoneInfo(timezone_name)
        result = _without_unrequested_whole_days(result, text, zone)
        result = _with_explicit_range_rescued(result, text, zone)
        return _with_bare_hour_resolved(
            result, text, reference_time, zone, self._limits.start_hour, self._limits.end_hour
        )

    def _rejection(
        self, result: "_AvailabilityOutput", reference_time: datetime, timezone_name: str
    ) -> DateCheck | None:
        """First deterministic failure among the interval fields; None when all are acceptable."""
        for window in result.intervals:
            problem = window.syntax_problem()
            if problem is not None:
                return problem
            interval = window.to_interval()
            local_start = interval.start.astimezone(ZoneInfo(timezone_name))
            if window.claimed_weekday.strip():
                weekday_check = validate_date_text(
                    local_start.date().isoformat(),
                    local_start.strftime("%H:%M"),
                    window.claimed_weekday,
                    reference_time,
                    timezone_name,
                    start_hour=self._limits.start_hour,
                    end_hour=self._limits.end_hour,
                    horizon_days=self._limits.horizon_days,
                )
                if weekday_check.code is DateErrorCode.WEEKDAY_MISMATCH:
                    return weekday_check
            check = validate_interval(
                interval,
                reference_time,
                timezone_name,
                start_hour=self._limits.start_hour,
                end_hour=self._limits.end_hour,
                horizon_days=self._limits.horizon_days,
            )
            if not check.valid:
                return check
        for window in result.suggested_intervals:
            problem = window.syntax_problem()
            if problem is not None:
                return problem
        return None

    def _literal_date_problem(
        self, text: str, reference_time: datetime, timezone_name: str
    ) -> DateCheck | None:
        """Backstop for ISO dates written literally when the model returned nothing for them."""
        for match in _ISO_DATE.finditer(text):
            clock = _CLOCK.search(text, match.end())
            check = validate_date_text(
                match.group(),
                clock.group() if clock else None,
                None,
                reference_time,
                timezone_name,
                start_hour=self._limits.start_hour,
                end_hour=self._limits.end_hour,
                horizon_days=self._limits.horizon_days,
            )
            if not check.valid:
                return check
        return None

    async def _availability_json(
        self,
        prompt: str,
        reference_time: datetime,
        timezone_name: str,
        failed_checks: list[DateCheck],
    ) -> str:
        messages: list[dict[str, object]] = [{"role": "user", "content": prompt}]
        response = None
        for _ in range(4):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=600,
                thinking={"type": "disabled"},
                messages=messages,
                tools=[
                    _calendar_tool(),
                    _add_two_hour_end_tool(),
                    _resolve_range_tool(),
                    _resolve_bare_hour_tool(),
                    _validate_date_tool(),
                    *([_read_skill_tool(self._skills)] if self._skills else []),
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
                block for block in response.content if getattr(block, "type", None) == "tool_use"
            ]
            if not tool_calls:
                break
            for block in tool_calls:
                if getattr(block, "name", "") == "validate_date":
                    check = _validate_date_call(
                        getattr(block, "input", {}), reference_time, timezone_name, self._limits
                    )
                    if not check.valid:
                        failed_checks.append(check)
            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {
                    "role": "user",
                    "content": _availability_tool_results(
                        tool_calls, reference_time, timezone_name, self._limits
                    ),
                }
            )
        return next(
            (block.text for block in response.content if getattr(block, "type", None) == "text"),
            "",
        )

    async def interpret_decision(self, text: str, role: ParticipantRole) -> DecisionInterpretation:
        """Read an explicit yes/no only; anything else becomes a clarification."""
        decision = interpret_explicit_decision(text)
        return DecisionInterpretation(decision, decision is None)

    async def compose(self, intent: str, language: str, facts: dict[str, str]) -> str:
        return await self._text(build_composition_prompt(intent, language, facts), 300)

    async def compose_slot_reply(self, language: str, facts: dict[str, str]) -> tuple[str, str]:
        """Return LLM intro/ask prose; the deterministic table is injected by the caller."""
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=300,
            thinking={"type": "disabled"},
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

    async def detect_language(self, text: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=50,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": build_language_detect_prompt(text)}],
            output_config={"format": {"type": "json_schema", "schema": _LANGUAGE_SCHEMA}},
        )
        output = _structured_output(response, _LanguageOutput, "detect_language")
        return output.language.strip().lower()

    async def translate(self, text: str, language: str) -> str:
        return await self._text(build_translate_prompt(text, language), 400)


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


def _claims_intervals_without_any(output: "_AvailabilityOutput") -> bool:
    """An explicit_intervals verdict that carries no interval is a lazy reply worth retrying."""
    return (
        output.classification == MessageClass.EXPLICIT_INTERVALS
        and not output.intervals
        and not output.suggested_intervals
        and not output.mentioned_dates
    )


_WHOLE_DAY_TEXT = re.compile(
    r"todo el d[ií]a|d[ií]a completo|d[ií]a entero|all day|whole day|entire day|full day"
    r"|medianoche|midnight|\b(?:00:00|23:59|24:00)\b",
    re.IGNORECASE,
)
_ISO_DAY = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_CLOCK_RANGE = re.compile(
    r"\b(\d{1,2}:\d{2})\s*(?:a|to|-|\u2013|hasta|until|y|and)\s*(\d{1,2}:\d{2})\b",
    re.IGNORECASE,
)
_BARE_HOUR = re.compile(
    r"\b(?:a\s+las?|at|around|about|sobre\s+las|hacia\s+las|sobre\s+la)\s+(\d{1,2})\b"
    r"(?!\s*(?::|\.\d|h\b|a\.?m|p\.?m|de\s+la|por\s+la|in\s+the|a\s+\d|to\s+\d|-|hasta"
    r"|y\s+media|y\s+cuarto))",
    re.IGNORECASE,
)


def _misses_obvious_interval(output: "_AvailabilityOutput", text: str) -> bool:
    """A literal ISO date plus clock range that produced no interval and no question: retry."""
    return (
        not output.intervals
        and not output.suggested_intervals
        and not output.clarification_required
        and _literal_range(text) is not None
    )


def _literal_range(text: str) -> tuple[date, time, time] | None:
    """The one ISO date with the one HH:MM-HH:MM range in the text; None when not unambiguous."""
    days = set(_ISO_DAY.findall(text))
    ranges = _CLOCK_RANGE.findall(text)
    if len(days) != 1 or len(ranges) != 1:
        return None
    try:
        day = date(*(int(part) for part in next(iter(days))))
        start, end = (time.fromisoformat(part.zfill(5)) for part in ranges[0])
    except ValueError:
        return None
    return (day, start, end) if start < end else None


def _local_window(day: date, start: time, end: time, zone: ZoneInfo) -> "_WindowOutput":
    return _WindowOutput(
        start=datetime.combine(day, start, zone).isoformat(),
        end=datetime.combine(day, end, zone).isoformat(),
    )


def _with_explicit_range_rescued(
    output: "_AvailabilityOutput", text: str, zone: ZoneInfo
) -> "_AvailabilityOutput":
    if not _misses_obvious_interval(output, text):
        return output
    literal = _literal_range(text)
    assert literal is not None
    window = _local_window(*literal, zone)
    return output.model_copy(
        update={
            "intervals": [window],
            "complete": True,
            "clarification_required": False,
            "clarification": "",
            "classification": MessageClass.EXPLICIT_INTERVALS.value,
        }
    )


def _without_unrequested_whole_days(
    output: "_AvailabilityOutput", text: str, zone: ZoneInfo
) -> "_AvailabilityOutput":
    """Drop day-long intervals the text never asked for; they become a vague date request."""
    if _WHOLE_DAY_TEXT.search(text):
        return output
    kept, days = [], []
    for window in output.intervals:
        try:
            start = datetime.fromisoformat(window.start).astimezone(zone)
            end = datetime.fromisoformat(window.end).astimezone(zone)
        except ValueError:
            kept.append(window)
            continue
        whole_day = end - start >= timedelta(hours=8) and (
            start.time() == time(0, 0) or (end.hour, end.minute) in {(23, 59), (0, 0)}
        )
        if whole_day:
            days.extend((start.date(), end.date()))
        else:
            kept.append(window)
    if not days:
        return output
    if kept:
        return output.model_copy(update={"intervals": kept})
    return output.model_copy(
        update={
            "intervals": [],
            "suggested_intervals": [],
            "complete": False,
            "clarification_required": True,
            "date_confirmation_required": False,
            "classification": MessageClass.VAGUE_DATE_REQUEST.value,
            "ambiguity_reason": AmbiguityReason.UNSPECIFIED_TIME.value,
            "date_from": output.date_from or min(days).isoformat(),
            "date_to": output.date_to or max(days).isoformat(),
        }
    )


_WEEKDAY_INDEX = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}  # fmt: skip


def _named_day(output: "_AvailabilityOutput", reference_time: datetime, zone: ZoneInfo):
    """The one day the model located: date_from, or the next occurrence of a lone weekday."""
    if output.date_from and output.date_from == output.date_to:
        try:
            return date.fromisoformat(output.date_from)
        except ValueError:
            return None
    weekdays = {
        _WEEKDAY_INDEX[mention.weekday.strip().lower()]
        for mention in output.mentioned_dates
        if mention.weekday.strip().lower() in _WEEKDAY_INDEX and mention.day is None
    }
    if len(weekdays) != 1:
        return None
    today = reference_time.astimezone(zone).date()
    ahead = (weekdays.pop() - today.weekday()) % 7
    return today + timedelta(days=ahead) if ahead else None


def _with_bare_hour_resolved(
    output: "_AvailabilityOutput",
    text: str,
    reference_time: datetime,
    zone: ZoneInfo,
    start_hour: int,
    end_hour: int,
) -> "_AvailabilityOutput":
    """A bare hour ('a las 10') is settled by the visit hours, never by the model's AM/PM guess."""
    matches = _BARE_HOUR.findall(text)
    if len(matches) != 1 or _CLOCK.search(text) or len(re.findall(r"\d+", text)) > 2:
        return output
    hour = resolve_bare_hour(int(matches[0]), start_hour, end_hour)
    if hour is None or output.suggested_intervals or len(output.intervals) > 1:
        return output
    if output.intervals:
        try:
            start = datetime.fromisoformat(output.intervals[0].start).astimezone(zone)
        except ValueError:
            return output
        if start.hour == hour or start.hour not in (
            int(matches[0]) % 12,
            int(matches[0]) % 12 + 12,
        ):
            return output
        day = start.date()
    elif output.classification in (
        MessageClass.VAGUE_DATE_REQUEST,
        MessageClass.EXPLICIT_INTERVALS,
        MessageClass.UNCLASSIFIED,
    ) and output.part_of_day in ("", PartOfDay.NONE.value):
        day = _named_day(output, reference_time, zone)
        if day is None:
            return output
    else:
        return output
    interval = visit_interval_from_start(datetime.combine(day, time(hour), zone), zone.key)
    window = _WindowOutput(
        start=interval.start.isoformat(),
        end=interval.end.isoformat(),
        claimed_weekday=output.intervals[0].claimed_weekday if output.intervals else "",
    )
    return output.model_copy(
        update={
            "intervals": [window],
            "complete": True,
            "clarification_required": False,
            "clarification": "",
            "classification": MessageClass.EXPLICIT_INTERVALS.value,
            "ambiguity_reason": AmbiguityReason.OTHER.value,
            "date_from": "",
            "date_to": "",
        }
    )


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

_LANGUAGE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"language": {"type": "string"}},
    "required": ["language"],
    "additionalProperties": False,
}


def _availability_schema() -> dict[str, object]:
    """Return the constrained Anthropic JSON schema for availability interpretation."""
    window = {
        "type": "object",
        "properties": {
            "start": {"type": "string"},
            "end": {"type": "string"},
            "claimed_weekday": {"type": "string"},
        },
        "required": ["start", "end", "claimed_weekday"],
        "additionalProperties": False,
    }
    nullable_int = {"type": ["integer", "null"]}
    mentioned = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "day": nullable_int,
            "month": nullable_int,
            "year": nullable_int,
            "hour": nullable_int,
            "minute": nullable_int,
            "weekday": {"type": "string"},
            "relative": {"type": "boolean"},
        },
        "required": ["text", "day", "month", "year", "hour", "minute", "weekday", "relative"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "mentioned_dates": {"type": "array", "items": mentioned},
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
            "mentioned_dates",
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


def _resolve_bare_hour_tool() -> dict[str, object]:
    return {
        "name": "resolve_bare_hour",
        "description": (
            "Resolve a bare hour written without AM/PM or part of day (for example 'a las 10' "
            "or 'at 3') into its 24-hour value using the visit hours. Returns hour_24, or null "
            "when the visit hours leave zero or two readings (then the hour is ambiguous). "
            "Always use it for such hours instead of reasoning about AM/PM yourself."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"hour": {"type": "integer"}},
            "required": ["hour"],
            "additionalProperties": False,
        },
    }


def _validate_date_call(
    arguments: dict, reference_time: datetime, timezone_name: str, limits: _DateLimits
) -> DateCheck:
    return validate_date_text(
        str(arguments.get("date", "")),
        arguments.get("time"),
        arguments.get("claimed_weekday"),
        reference_time,
        timezone_name,
        start_hour=limits.start_hour,
        end_hour=limits.end_hour,
        horizon_days=limits.horizon_days,
    )


def _validate_date_tool() -> dict[str, object]:
    optional_text = {"type": ["string", "null"]}
    return {
        "name": "validate_date",
        "description": (
            "Check a participant-supplied date before returning it. Pass the ISO date exactly as "
            "the participant stated it (never corrected), the start time as HH:MM when given, and "
            "the weekday name when the participant stated one. Returns valid, or a code, reason, "
            "actual_weekday and nearest_valid. Call it for every date the participant gives."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "time": optional_text,
                "claimed_weekday": optional_text,
            },
            "required": ["date", "time", "claimed_weekday"],
            "additionalProperties": False,
        },
    }


def _read_skill_tool(skills: dict[str, object]) -> dict[str, object]:
    return {
        "name": "read_skill",
        "description": (
            "Read the full text of a skill from the catalogue in the prompt. Call it only when "
            "its description says it applies to the message; skip it otherwise."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "enum": list(skills)}},
            "required": ["name"],
            "additionalProperties": False,
        },
    }


def _availability_tool_results(
    tool_calls: list[object],
    reference_time: datetime,
    timezone_name: str,
    limits: _DateLimits = _DateLimits(),
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
        elif name == "resolve_bare_hour":
            hour = arguments.get("hour")
            result = {
                "hour_24": resolve_bare_hour(hour, limits.start_hour, limits.end_hour)
                if isinstance(hour, int)
                else None
            }
        elif name == "validate_date":
            check = _validate_date_call(arguments, reference_time, timezone_name, limits)
            result = {key: value for key, value in asdict(check).items() if value not in (None, "")}
            result["valid"] = check.valid
            if check.code is not None:
                result["code"] = check.code.value
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
