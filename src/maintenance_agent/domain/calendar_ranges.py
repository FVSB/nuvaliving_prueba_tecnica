"""Deterministic resolution of relative periods into local date ranges (tool backend)."""

from dataclasses import dataclass
from datetime import date, timedelta

KINDS = ("today", "tomorrow", "day_after_tomorrow", "this_week", "next_week", "weekend")


@dataclass(frozen=True, slots=True)
class DateRange:
    date_from: date
    date_to: date  # inclusive

    def days(self) -> list[date]:
        count = (self.date_to - self.date_from).days + 1
        return [self.date_from + timedelta(days=n) for n in range(count)]


def resolve_range(today: date, kind: str) -> DateRange | None:
    """Resolve a whole period against today; never returns days before today."""
    if kind not in KINDS:
        return None
    if kind == "today":
        return DateRange(today, today)
    if kind == "tomorrow":
        return DateRange(today + timedelta(days=1), today + timedelta(days=1))
    if kind == "day_after_tomorrow":
        return DateRange(today + timedelta(days=2), today + timedelta(days=2))
    monday = today - timedelta(days=today.weekday())
    if kind == "weekend":
        saturday = monday + timedelta(days=5)
        if saturday + timedelta(days=1) < today:
            saturday += timedelta(days=7)
        return _clamp(saturday, saturday + timedelta(days=1), today)
    if kind == "next_week":
        monday += timedelta(days=7)
    return _clamp(monday, monday + timedelta(days=6), today)


def _clamp(start: date, end: date, today: date) -> DateRange | None:
    start = max(start, today)
    return DateRange(start, end) if start <= end else None
