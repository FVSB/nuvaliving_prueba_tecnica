"""Strict extraction prompt for participant supplied visit windows."""

import json
from datetime import datetime

from maintenance_agent.domain.negotiation import ParticipantRole
from maintenance_agent.skills import skill_index


def build_availability_prompt(
    text: str,
    role: ParticipantRole,
    reference_time: datetime,
    timezone_name: str,
) -> str:
    return (
        "Interpret availability and return intervals, suggested_intervals, complete, "
        "clarification_required, date_confirmation_required, weekday_is_today, clarification, "
        "classification, date_from, date_to, part_of_day, and ambiguity_reason. classification is one of: explicit_intervals (at least one "
        "fully specified interval was supplied or clearly referenced), vague_date_request "
        "(the message asks about possible days or times, uses vague or relative date "
        "expressions, or names a time that stays ambiguous), decision (an explicit yes/no "
        "answer to a pending proposal), or unclassified (anything else). A message mixing "
        "an explicit interval with a vague question is explicit_intervals. A relative date "
        "with an unambiguous time of day (for example tomorrow at 2 in the afternoon) is "
        "explicit_intervals; the same date with a bare hour whose AM/PM is ambiguous "
        "(for example tomorrow at 2) is vague_date_request, and in that case leave "
        "intervals and suggested_intervals empty. For vague_date_request set requested_date to "
        "the single local ISO date the participant means (resolve relative words such as "
        "tomorrow with get_local_calendar_context) or an empty string when no single day is "
        "named; set part_of_day to morning (early, morning), afternoon, evening, or none; "
        "set ambiguity_reason to unspecified_time, unspecified_day, ambiguous_am_pm, or other. "
        "For every other classification use empty date_from and date_to, none, and other. "
        "Return every fully specified interval actually mentioned; one interval is sufficient. "
        "Do not ask for more dates just because only one or two were supplied. "
        "Set complete to true when every supplied interval has its required date and time details, "
        "even if the participant "
        "did not explicitly say these are all possible dates. Set it false only when details are "
        "missing for a stated interval. Resolve "
        "weekday words to ISO dates using the supplied reference time and timezone. The reference "
        "time is authoritative. A weekday meaning today must not become a same-day appointment: "
        "place its next-week occurrence in suggested_intervals and set date_confirmation_required; "
        "do not put that suggestion in intervals until the tenant confirms it. For any other "
        "relative "
        "weekday, also provide a concrete suggested interval and require tenant confirmation. Keep "
        "confirmed absolute dates in intervals. Interpret 12am as 00:00 and 12pm as 12:00. When a "
        "date and start time are supplied without an end time, call add_two_hour_end with that "
        "start and use the returned two-hour interval as a fully specified interval; the end is "
        "not missing, so do not ask for it and keep complete true. If AM/PM or a date is "
        "ambiguous, "
        "set clarification_required and provide a short clarification. Never invent a duration, "
        "timezone, availability interval, or consent. If a relative date or weekday needs "
        "resolving, "
        "call get_local_calendar_context and use its returned dates and weekdays. Every returned "
        "timestamp must include an offset. "
        "Visits are two hours, but tenant availability windows may be longer. Handyman output "
        "can be "
        "availability evidence only and never tenant consent.\n"
        "Available skills (read one with read_skill only when its description applies):\n"
        f"{skill_index()}\n"
        f"Participant role: {role.value}\nReference time: {reference_time.isoformat()}\n"
        f"Local timezone: {timezone_name}\nMessage: {json.dumps(text, ensure_ascii=False)}"
    )
