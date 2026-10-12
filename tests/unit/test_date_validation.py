from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from maintenance_agent.domain.date_validation import (
    DateErrorCode,
    check_timestamp_syntax,
    resolve_bare_hour,
    validate_date_text,
    validate_interval,
)
from maintenance_agent.domain.negotiation import TimeInterval

ZONE = "Europe/Madrid"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=ZoneInfo(ZONE))  # Monday
LIMITS = {"start_hour": 9, "end_hour": 19, "horizon_days": 7}


def check(date: str, time: str | None = None, weekday: str | None = None):
    return validate_date_text(date, time, weekday, NOW, ZONE, **LIMITS)


def interval(start: str, end: str) -> TimeInterval:
    return TimeInterval(datetime.fromisoformat(start), datetime.fromisoformat(end))


@pytest.mark.parametrize(
    ("date", "time", "weekday", "code"),
    [
        ("2026-02-30", "10:00", None, DateErrorCode.NOT_A_CALENDAR_DATE),
        ("2026-13-01", None, None, DateErrorCode.NOT_A_CALENDAR_DATE),
        ("2027-04-31", "10:00", None, DateErrorCode.NOT_A_CALENDAR_DATE),
        ("2026-10-13", "25:00", None, DateErrorCode.INVALID_TIME),
        ("2026-10-13", "24:30", None, DateErrorCode.INVALID_TIME),
        ("2026-10-11", "10:00", None, DateErrorCode.IN_THE_PAST),
        ("2025-10-13", "10:00", None, DateErrorCode.IN_THE_PAST),
        ("2026-10-12", "09:00", None, DateErrorCode.IN_THE_PAST),
        ("2062-10-20", "10:00", None, DateErrorCode.TOO_FAR_AHEAD),
        ("2026-10-20", None, None, DateErrorCode.TOO_FAR_AHEAD),
        ("2026-10-15", "10:00", "lunes", DateErrorCode.WEEKDAY_MISMATCH),
        ("2026-10-13", "03:00", None, DateErrorCode.OUTSIDE_VISIT_HOURS),
        ("2026-10-13", "19:00", None, DateErrorCode.OUTSIDE_VISIT_HOURS),
    ],
)
def test_invalid_dates_report_their_code(date, time, weekday, code) -> None:
    result = check(date, time, weekday)
    assert not result.valid and result.code is code and result.reason


@pytest.mark.parametrize(
    ("date", "time", "weekday"),
    [
        ("2026-10-13", "10:00", None),
        ("2026-10-19", "18:00", "Monday"),  # horizon edge: today + 7 days
        ("2026-10-12", "15:00", None),  # later today
        ("2026-10-13", None, "martes"),
    ],
)
def test_valid_dates(date, time, weekday) -> None:
    assert check(date, time, weekday).valid


def test_nearest_valid_for_impossible_day_is_end_of_month() -> None:
    assert check("2026-10-32").nearest_valid is None
    assert check("2026-13-01").nearest_valid is None
    assert check("2026-11-31").nearest_valid is None  # 2026-11-30 is beyond the horizon


@pytest.mark.parametrize(
    ("date", "time", "weekday", "expected"),
    [
        ("2026-02-30", "10:00", None, None),  # the 28th is in the past
        ("2027-04-31", "10:00", None, None),  # the 30th is beyond the horizon
        ("2026-10-15", "10:00", "lunes", "2026-10-19"),  # Monday 12 10:00 already passed
        ("2026-10-15", None, "lunes", "2026-10-12"),  # closest valid Monday (today)
        ("2026-10-18", None, "martes", "2026-10-13"),
        ("2026-10-15", None, "sábado", "2026-10-17"),
        ("2026-12-03", None, "lunes", "2026-10-19"),  # farthest case still inside the horizon
        ("2026-10-12", "03:00", None, None),  # 09:00 today already passed
        ("2026-10-13", "03:00", None, "2026-10-13T09:00"),
        ("2026-10-19", "20:00", None, "2026-10-19T18:00"),
        ("2026-10-12", "20:00", None, "2026-10-12T18:00"),
    ],
)
def test_nearest_valid_always_passes_the_same_checks(date, time, weekday, expected) -> None:
    result = check(date, time, weekday)
    assert not result.valid
    assert result.nearest_valid == expected
    if expected is not None:
        day, _, clock = expected.partition("T")
        assert check(day, clock or None).valid


def test_interval_nearest_in_the_past_is_dropped() -> None:
    past = validate_interval(
        interval("2026-10-12T03:00+02:00", "2026-10-12T05:00+02:00"), NOW, ZONE, **LIMITS
    )
    assert past.code is DateErrorCode.IN_THE_PAST
    assert past.nearest_valid is None
    beyond = validate_interval(
        interval("2026-10-19T18:00+02:00", "2026-10-19T20:00+02:00"), NOW, ZONE, **LIMITS
    )
    assert beyond.nearest_valid == "2026-10-19T17:00:00+02:00"


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (10, 10),
        (3, 15),
        (9, 9),
        (12, 12),
        (2, 14),
        (6, 18),
        (7, None),
        (8, None),
        (13, 13),
        (20, None),
        (24, None),
        (-1, None),
        (0, None),
    ],
)
def test_resolve_bare_hour_uses_visit_window(hour, expected) -> None:
    assert resolve_bare_hour(hour, 9, 19) == expected


def test_resolve_bare_hour_two_readings_inside_the_window_is_ambiguous() -> None:
    assert resolve_bare_hour(3, 0, 24) is None


def test_weekday_mismatch_reports_actual_weekday_and_nearest_future_date() -> None:
    result = check("2026-10-15", "10:00", "lunes")
    assert result.actual_weekday == "Thursday"
    assert result.nearest_valid == "2026-10-19"
    assert check("2026-10-15", None, "sábado").nearest_valid == "2026-10-17"


def test_outside_hours_suggests_nearest_start() -> None:
    assert check("2026-10-13", "03:00").nearest_valid == "2026-10-13T09:00"
    assert check("2026-10-13", "20:00").nearest_valid == "2026-10-13T18:00"


def test_interval_valid_and_horizon_edge() -> None:
    assert validate_interval(
        interval("2026-10-13T10:00+02:00", "2026-10-13T12:00+02:00"), NOW, ZONE, **LIMITS
    ).valid
    assert validate_interval(
        interval("2026-10-19T17:00+02:00", "2026-10-19T19:00+02:00"), NOW, ZONE, **LIMITS
    ).valid
    over = validate_interval(
        interval("2026-10-20T10:00+02:00", "2026-10-20T12:00+02:00"), NOW, ZONE, **LIMITS
    )
    assert over.code is DateErrorCode.TOO_FAR_AHEAD


def test_interval_outside_hours_and_crossing_the_end() -> None:
    early = validate_interval(
        interval("2026-10-13T03:00+02:00", "2026-10-13T05:00+02:00"), NOW, ZONE, **LIMITS
    )
    assert early.code is DateErrorCode.OUTSIDE_VISIT_HOURS
    assert early.nearest_valid == "2026-10-13T09:00:00+02:00"
    crossing = validate_interval(
        interval("2026-10-13T18:00+02:00", "2026-10-13T20:00+02:00"), NOW, ZONE, **LIMITS
    )
    assert crossing.code is DateErrorCode.OUTSIDE_VISIT_HOURS
    assert crossing.nearest_valid == "2026-10-13T17:00:00+02:00"


def test_interval_in_the_past_uses_local_clock() -> None:
    past = validate_interval(
        interval("2026-10-12T09:00+02:00", "2026-10-12T11:00+02:00"), NOW, ZONE, **LIMITS
    )
    assert past.code is DateErrorCode.IN_THE_PAST


def test_timestamp_syntax_diagnosis() -> None:
    assert check_timestamp_syntax("2026-10-13T10:00:00+02:00") is None
    assert check_timestamp_syntax("2026-02-30T10:00:00+01:00").code is (
        DateErrorCode.NOT_A_CALENDAR_DATE
    )
    assert check_timestamp_syntax("2026-10-13T25:00:00+02:00").code is DateErrorCode.INVALID_TIME
    assert check_timestamp_syntax("2026-10-13T10:00:00").code is DateErrorCode.INVALID_TIME


def mention(**fields):
    from maintenance_agent.domain.date_validation import MentionedDate, validate_mentioned_date

    return validate_mentioned_date(MentionedDate(text="x", **fields), NOW, ZONE, **LIMITS)


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"day": 31, "month": 4, "year": 2027, "hour": 10}, DateErrorCode.NOT_A_CALENDAR_DATE),
        ({"day": 31, "month": 4, "hour": 10}, DateErrorCode.NOT_A_CALENDAR_DATE),
        ({"day": 30, "month": 2, "year": 2026, "hour": 10}, DateErrorCode.NOT_A_CALENDAR_DATE),
        ({"day": 29, "month": 2, "year": 2027}, DateErrorCode.NOT_A_CALENDAR_DATE),
        ({"day": 5, "month": 13}, DateErrorCode.NOT_A_CALENDAR_DATE),
        ({"day": 32, "month": 10}, DateErrorCode.NOT_A_CALENDAR_DATE),
        ({"day": 13, "month": 10, "year": 2026, "hour": 25}, DateErrorCode.INVALID_TIME),
        (
            {"day": 13, "month": 10, "year": 2026, "hour": 24, "minute": 30},
            DateErrorCode.INVALID_TIME,
        ),
        ({"hour": 10, "minute": 60}, DateErrorCode.INVALID_TIME),
        ({"hour": 25, "relative": True}, DateErrorCode.INVALID_TIME),
        ({"day": 1, "month": 10, "year": 2026, "hour": 10}, DateErrorCode.IN_THE_PAST),
        ({"day": 1, "month": 10, "hour": 10}, DateErrorCode.TOO_FAR_AHEAD),
        ({"day": 20, "month": 10, "year": 2062, "hour": 10}, DateErrorCode.TOO_FAR_AHEAD),
        (
            {"day": 15, "month": 10, "year": 2026, "hour": 10, "weekday": "Monday"},
            DateErrorCode.WEEKDAY_MISMATCH,
        ),
        ({"day": 13, "month": 10, "year": 2026, "hour": 3}, DateErrorCode.OUTSIDE_VISIT_HOURS),
        ({"day": 13, "month": 10, "hour": 24}, DateErrorCode.OUTSIDE_VISIT_HOURS),
    ],
)
def test_mentioned_date_components_are_rejected(fields, code) -> None:
    result = mention(**fields)
    assert not result.valid and result.code is code


@pytest.mark.parametrize(
    "fields",
    [
        {"day": 13, "month": 10, "year": 2026, "hour": 10, "weekday": "Tuesday"},
        {"day": 13, "month": 10, "hour": 10, "minute": 30},
        {"day": 12, "month": 10, "hour": 15},
        {"relative": True, "weekday": "Friday"},
        {"relative": True, "hour": 10},
        {"hour": 12},
        {"weekday": "Monday"},
        {"month": 10},
    ],
)
def test_mentioned_date_components_valid_or_not_checkable(fields) -> None:
    assert mention(**fields).valid


def test_missing_year_uses_next_future_occurrence() -> None:
    assert mention(day=11, month=10, hour=10).code is DateErrorCode.TOO_FAR_AHEAD
    assert mention(day=29, month=2).code is DateErrorCode.TOO_FAR_AHEAD
