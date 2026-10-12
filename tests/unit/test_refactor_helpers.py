"""Characterization of the helpers consolidated by specs/007-solid-refactor (Phase 1).

These pin the behaviour the duplicated code had, so the single shared definitions cannot drift.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from maintenance_agent.domain.date_validation import validate_date_text
from maintenance_agent.domain.decisions import interpret_cancellation, interpret_explicit_decision
from maintenance_agent.domain.negotiation import DecisionValue, TimeInterval
from maintenance_agent.domain.scheduling import overlaps
from maintenance_agent.domain.text import fold
from maintenance_agent.domain.weekdays import (
    WEEKDAY_INDEX,
    WEEKDAYS_EN,
    WEEKDAYS_ES,
    weekday_name_en,
)


def _utc(hour: int) -> datetime:
    return datetime(2026, 10, 13, hour, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Sí", "si"), ("MIÉRCOLES", "miercoles"), ("Ñandú", "nandu"), ("plain", "plain")],
)
def test_fold_casefolds_and_strips_diacritics(text: str, expected: str) -> None:
    assert fold(text) == expected


@pytest.mark.parametrize("text", ["sí", "SI", "Sí.", "  si  "])
def test_explicit_yes_survives_folding(text: str) -> None:
    assert interpret_explicit_decision(text) is DecisionValue.YES


def test_cancellation_detected_with_accents_and_case() -> None:
    assert interpret_cancellation("YA NO ME INTERESA")
    assert interpret_cancellation("ya no me sirvé")


def test_weekday_names_are_monday_first_in_both_languages() -> None:
    assert WEEKDAYS_EN[0] == "Monday" and WEEKDAYS_EN[6] == "Sunday"
    assert WEEKDAYS_ES[0] == "lunes" and WEEKDAYS_ES[6] == "domingo"


def test_weekday_index_accepts_accented_and_unaccented_spanish() -> None:
    assert WEEKDAY_INDEX["miércoles"] == WEEKDAY_INDEX["miercoles"] == 2
    assert WEEKDAY_INDEX["sábado"] == WEEKDAY_INDEX["sabado"] == 5
    assert WEEKDAY_INDEX["monday"] == 0


def test_weekday_name_en_matches_standard_calendar_names() -> None:
    assert weekday_name_en(date(2026, 10, 13)) == "Tuesday"


def test_claimed_weekday_mismatch_is_still_rejected() -> None:
    result = validate_date_text(
        "2026-10-13",
        None,
        "lunes",
        datetime(2026, 10, 12, 12, tzinfo=timezone.utc),
        "Europe/Madrid",
        start_hour=9,
        end_hour=19,
        horizon_days=7,
    )
    assert not result.valid
    assert result.actual_weekday == "Tuesday"


def test_claimed_spanish_weekday_matches_when_correct() -> None:
    result = validate_date_text(
        "2026-10-13",
        None,
        "martes",
        datetime(2026, 10, 12, 12, tzinfo=timezone.utc),
        "Europe/Madrid",
        start_hour=9,
        end_hour=19,
        horizon_days=7,
    )
    assert result.valid


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ((9, 11), (10, 12), True),
        ((9, 11), (11, 13), False),  # touching intervals do not overlap (semi-open)
        ((9, 11), (12, 13), False),
    ],
)
def test_overlaps_is_semi_open(
    left: tuple[int, int], right: tuple[int, int], expected: bool
) -> None:
    a = TimeInterval(_utc(left[0]), _utc(left[1]))
    b = TimeInterval(_utc(right[0]), _utc(right[1]))
    assert overlaps(a, b) is expected
    assert overlaps(b, a) is expected


def test_overlaps_with_one_hour_offset_gap() -> None:
    a = TimeInterval(_utc(9), _utc(11))
    b = TimeInterval(_utc(11) + timedelta(minutes=1), _utc(12))
    assert not overlaps(a, b)
