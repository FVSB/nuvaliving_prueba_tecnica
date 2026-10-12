from datetime import date

import pytest

from maintenance_agent.domain.calendar_ranges import resolve_range

MONDAY = date(2026, 10, 12)
WEDNESDAY = date(2026, 10, 14)


@pytest.mark.parametrize(
    ("today", "kind", "expected"),
    [
        (MONDAY, "tomorrow", ("2026-10-13", "2026-10-13")),
        (MONDAY, "next_week", ("2026-10-19", "2026-10-25")),
        (WEDNESDAY, "this_week", ("2026-10-14", "2026-10-18")),
        (MONDAY, "weekend", ("2026-10-17", "2026-10-18")),
        (date(2026, 10, 18), "weekend", ("2026-10-18", "2026-10-18")),
    ],
)
def test_periods_are_deterministic_and_never_in_the_past(today, kind, expected) -> None:
    result = resolve_range(today, kind)
    assert (result.date_from.isoformat(), result.date_to.isoformat()) == expected


def test_days_listing_and_unknown_kind() -> None:
    assert len(resolve_range(MONDAY, "next_week").days()) == 7
    assert resolve_range(MONDAY, "someday") is None
