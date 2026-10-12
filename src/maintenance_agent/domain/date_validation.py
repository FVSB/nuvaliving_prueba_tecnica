"""Deterministic validation of participant-supplied dates, times and visit intervals."""

import calendar
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from maintenance_agent.domain.negotiation import TimeInterval

_WEEKDAYS = {
    "monday": 0,
    "lunes": 0,
    "tuesday": 1,
    "martes": 1,
    "wednesday": 2,
    "miercoles": 2,
    "miércoles": 2,
    "thursday": 3,
    "jueves": 3,
    "friday": 4,
    "viernes": 4,
    "saturday": 5,
    "sabado": 5,
    "sábado": 5,
    "sunday": 6,
    "domingo": 6,
}


class DateErrorCode(StrEnum):
    NOT_A_CALENDAR_DATE = "not_a_calendar_date"
    INVALID_TIME = "invalid_time"
    IN_THE_PAST = "in_the_past"
    WEEKDAY_MISMATCH = "weekday_mismatch"
    TOO_FAR_AHEAD = "too_far_ahead"
    OUTSIDE_VISIT_HOURS = "outside_visit_hours"


@dataclass(frozen=True, slots=True)
class DateCheck:
    valid: bool
    code: DateErrorCode | None = None
    reason: str = ""
    actual_weekday: str | None = None
    nearest_valid: str | None = None


_VALID = DateCheck(True)


def validate_interval(
    interval: TimeInterval,
    now: datetime,
    timezone_name: str,
    *,
    start_hour: int,
    end_hour: int,
    horizon_days: int,
) -> DateCheck:
    """Check a visit interval against the clock, the horizon and the visit hours."""
    zone = ZoneInfo(timezone_name)
    local_now = _local(now, zone)
    start, end = interval.start.astimezone(zone), interval.end.astimezone(zone)
    if start < local_now:
        return DateCheck(
            False,
            DateErrorCode.IN_THE_PAST,
            f"{start.isoformat()} is before the current time {local_now.isoformat()}.",
        )
    last_day = local_now.date() + timedelta(days=horizon_days)
    if start.date() > last_day:
        return DateCheck(
            False,
            DateErrorCode.TOO_FAR_AHEAD,
            f"{start.date().isoformat()} is more than {horizon_days} days ahead "
            f"(latest allowed date is {last_day.isoformat()}).",
            _weekday_name(start.date()),
        )
    day_start = datetime.combine(start.date(), time(start_hour), zone)
    day_end = datetime.combine(start.date(), time(end_hour % 24), zone)
    if end_hour == 24:
        day_end += timedelta(days=1)
    if start < day_start or end > day_end:
        nearest = None
        duration = end - start
        if start < day_start and day_start + duration <= day_end:
            nearest = day_start.isoformat()
        elif end > day_end and day_end - duration >= day_start:
            nearest = (day_end - duration).isoformat()
        return DateCheck(
            False,
            DateErrorCode.OUTSIDE_VISIT_HOURS,
            f"Visits must fit between {start_hour:02d}:00 and {end_hour:02d}:00 local time; "
            f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')} does not.",
            nearest_valid=_acceptable(nearest, local_now, zone, start_hour, end_hour, horizon_days),
        )
    return _VALID


def validate_date_text(
    date: str,
    time: str | None,
    claimed_weekday: str | None,
    now: datetime,
    timezone_name: str,
    *,
    start_hour: int,
    end_hour: int,
    horizon_days: int,
) -> DateCheck:
    """Check an ISO date, optional HH:MM start time and optional weekday claim."""
    zone = ZoneInfo(timezone_name)
    local_now = _local(now, zone)
    parsed = _parse_date(date)
    if isinstance(parsed, DateCheck):
        return replace(
            parsed,
            nearest_valid=_acceptable(
                parsed.nearest_valid, local_now, zone, start_hour, end_hour, horizon_days
            ),
        )
    clock = _parse_time(time)
    if isinstance(clock, DateCheck):
        return clock
    actual = _weekday_name(parsed)
    claimed_index = _WEEKDAYS.get((claimed_weekday or "").strip().lower())
    if claimed_weekday and claimed_weekday.strip() and claimed_index is None:
        return DateCheck(
            False,
            DateErrorCode.WEEKDAY_MISMATCH,
            f"'{claimed_weekday}' is not a weekday name; {parsed.isoformat()} is a {actual}.",
            actual,
        )
    if claimed_index is not None and claimed_index != parsed.weekday():
        nearest = _nearest_with_weekday(
            parsed, claimed_index, clock, local_now, zone, start_hour, end_hour, horizon_days
        )
        return DateCheck(
            False,
            DateErrorCode.WEEKDAY_MISMATCH,
            f"{parsed.isoformat()} is a {actual}, not a {claimed_weekday.strip()}.",
            actual,
            nearest,
        )
    today = local_now.date()
    if parsed < today or (clock is not None and datetime.combine(parsed, clock, zone) < local_now):
        return DateCheck(
            False,
            DateErrorCode.IN_THE_PAST,
            f"{parsed.isoformat()}{' ' + time if time else ''} is before the current time "
            f"{local_now.isoformat()}.",
            actual,
        )
    last_day = today + timedelta(days=horizon_days)
    if parsed > last_day:
        return DateCheck(
            False,
            DateErrorCode.TOO_FAR_AHEAD,
            f"{parsed.isoformat()} is more than {horizon_days} days ahead "
            f"(latest allowed date is {last_day.isoformat()}).",
            actual,
        )
    if clock is not None and not start_hour <= clock.hour < end_hour:
        nearest = _time_on(parsed, start_hour if clock.hour < start_hour else end_hour - 1)
        return DateCheck(
            False,
            DateErrorCode.OUTSIDE_VISIT_HOURS,
            f"Visits must fit between {start_hour:02d}:00 and {end_hour:02d}:00 local time; "
            f"{clock.strftime('%H:%M')} is outside that range.",
            actual,
            _acceptable(nearest, local_now, zone, start_hour, end_hour, horizon_days),
        )
    return _VALID


def check_timestamp_syntax(text: str) -> DateCheck | None:
    """Explain why an ISO timestamp does not parse; None when it parses."""
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        pass
    else:
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return DateCheck(False, DateErrorCode.INVALID_TIME, f"'{text}' has no UTC offset.")
        return None
    date_part, _, rest = text.partition("T")
    parsed_date = _parse_date(date_part)
    if isinstance(parsed_date, DateCheck):
        return parsed_date
    clock = _parse_time(rest[:5] if rest else None)
    if isinstance(clock, DateCheck):
        return clock
    return DateCheck(False, DateErrorCode.INVALID_TIME, f"'{text}' is not a valid timestamp.")


def _local(now: datetime, zone: ZoneInfo) -> datetime:
    return now.replace(tzinfo=zone) if now.tzinfo is None else now.astimezone(zone)


def _weekday_name(day: date) -> str:
    return calendar.day_name[day.weekday()]


def resolve_bare_hour(hour: int, start_hour: int, end_hour: int) -> int | None:
    """The single 24h reading of a bare hour inside [start_hour, end_hour); None if 0 or 2 fit."""
    if not 1 <= hour <= 23:
        return None
    readings = {hour, hour + 12} if hour < 12 else {hour}
    fitting = [reading for reading in sorted(readings) if start_hour <= reading < end_hour]
    return fitting[0] if len(fitting) == 1 else None


def _acceptable(
    candidate: str | None,
    local_now: datetime,
    zone: ZoneInfo,
    start_hour: int,
    end_hour: int,
    horizon_days: int,
) -> str | None:
    """Keep a suggested ISO date or datetime only if it passes the same checks as any input."""
    if candidate is None:
        return None
    try:
        if "T" in candidate:
            moment = datetime.fromisoformat(candidate)
            moment = _local(moment, zone)
            day = moment.date()
            if moment < local_now or not start_hour <= moment.hour < end_hour:
                return None
        else:
            day = date.fromisoformat(candidate)
    except ValueError:
        return None
    today = local_now.date()
    return candidate if today <= day <= today + timedelta(days=horizon_days) else None


def _nearest_with_weekday(
    stated: date,
    weekday: int,
    clock: time | None,
    local_now: datetime,
    zone: ZoneInfo,
    start_hour: int,
    end_hour: int,
    horizon_days: int,
) -> str | None:
    """The valid day with that weekday closest to the stated date, inside the horizon."""
    today = local_now.date()
    options = []
    for offset in range(horizon_days + 1):
        day = today + timedelta(days=offset)
        if day.weekday() != weekday:
            continue
        if clock is not None and (
            datetime.combine(day, clock, zone) < local_now
            or not start_hour <= clock.hour < end_hour
        ):
            continue
        options.append(day)
    if not options:
        return None
    return min(options, key=lambda day: abs((day - stated).days)).isoformat()


def _time_on(day: date, hour: int) -> str:
    return f"{day.isoformat()}T{hour:02d}:00"


def _parse_date(text: str) -> date | DateCheck:
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        pass
    parts = text.strip().split("-")
    nearest = None
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        year, month, day = (int(part) for part in parts)
        if 1 <= year <= 9999 and 1 <= month <= 12 and day > 28:
            last = calendar.monthrange(year, month)[1]
            if day > last:
                nearest = date(year, month, last).isoformat()
    return DateCheck(
        False,
        DateErrorCode.NOT_A_CALENDAR_DATE,
        f"'{text}' is not a real calendar date.",
        nearest_valid=nearest,
    )


def _parse_time(text: str | None) -> time | DateCheck | None:
    if text is None or not text.strip():
        return None
    try:
        return time.fromisoformat(text.strip())
    except ValueError:
        return DateCheck(
            False,
            DateErrorCode.INVALID_TIME,
            f"'{text}' is not a valid 24-hour time (HH:MM, 00:00 to 23:59).",
        )


@dataclass(frozen=True, slots=True)
class MentionedDate:
    """A date or time exactly as the participant wrote it, split into components."""

    text: str = ""
    day: int | None = None
    month: int | None = None
    year: int | None = None
    hour: int | None = None
    minute: int | None = None
    weekday: str = ""
    relative: bool = False


def validate_mentioned_date(
    mention: MentionedDate,
    now: datetime,
    timezone_name: str,
    *,
    start_hour: int,
    end_hour: int,
    horizon_days: int,
) -> DateCheck:
    """Validate literal date components; relative mentions only get the checks that are exact."""
    clock_text = _clock_text(mention)
    if isinstance(clock_text, DateCheck):
        return clock_text
    if mention.relative:
        return _VALID
    if mention.day is not None and not 1 <= mention.day <= 31:
        return _not_a_date(mention, f"day {mention.day} does not exist in any month")
    if mention.month is not None and not 1 <= mention.month <= 12:
        return _not_a_date(mention, f"month {mention.month} does not exist")
    if mention.year is not None and not 1 <= mention.year <= 9999:
        return _not_a_date(mention, f"year {mention.year} is not a valid year")
    if mention.day is None or mention.month is None:
        return _VALID
    today = _local(now, ZoneInfo(timezone_name)).date()
    year = mention.year if mention.year is not None else _next_year(mention, today)
    if mention.day > calendar.monthrange(year, mention.month)[1]:
        zone = ZoneInfo(timezone_name)
        last_of_month = date(year, mention.month, calendar.monthrange(year, mention.month)[1])
        return _not_a_date(
            mention,
            f"{calendar.month_name[mention.month]} {year} has only "
            f"{calendar.monthrange(year, mention.month)[1]} days",
            _acceptable(
                last_of_month.isoformat(),
                _local(now, zone),
                zone,
                start_hour,
                end_hour,
                horizon_days,
            ),
        )
    return validate_date_text(
        date(year, mention.month, mention.day).isoformat(),
        clock_text,
        mention.weekday or None,
        now,
        timezone_name,
        start_hour=start_hour,
        end_hour=end_hour,
        horizon_days=horizon_days,
    )


def first_mention_problem(
    mentions: list[MentionedDate] | tuple[MentionedDate, ...],
    now: datetime,
    timezone_name: str,
    *,
    start_hour: int,
    end_hour: int,
    horizon_days: int,
) -> DateCheck | None:
    for mention in mentions:
        check = validate_mentioned_date(
            mention,
            now,
            timezone_name,
            start_hour=start_hour,
            end_hour=end_hour,
            horizon_days=horizon_days,
        )
        if not check.valid:
            return check
    return None


def _clock_text(mention: MentionedDate) -> str | DateCheck | None:
    if mention.hour is None:
        return None
    minute = mention.minute or 0
    label = f"{mention.hour:02d}:{minute:02d}"
    if not 0 <= mention.hour <= 24 or not 0 <= minute <= 59 or (mention.hour == 24 and minute):
        return DateCheck(
            False,
            DateErrorCode.INVALID_TIME,
            f"'{mention.text or label}' is not a valid 24-hour time (00:00 to 23:59).",
        )
    return "23:59" if mention.hour == 24 else label


def _not_a_date(mention: MentionedDate, why: str, nearest: str | None = None) -> DateCheck:
    return DateCheck(
        False,
        DateErrorCode.NOT_A_CALENDAR_DATE,
        f"'{mention.text}' is not a real calendar date: {why}.",
        nearest_valid=nearest,
    )


def _next_year(mention: MentionedDate, today: date) -> int:
    """Year of the next occurrence of day/month on or after today (any real one if none)."""
    assert mention.day is not None and mention.month is not None
    for year in range(today.year, today.year + 9):
        if mention.day <= calendar.monthrange(year, mention.month)[1] and (
            date(year, mention.month, mention.day) >= today
        ):
            return year
    return today.year
