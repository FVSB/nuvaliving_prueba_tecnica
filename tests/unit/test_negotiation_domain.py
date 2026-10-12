from datetime import datetime, timedelta, timezone

import pytest

from maintenance_agent.business_rules import active_rules
from maintenance_agent.domain.decisions import interpret_explicit_decision
from maintenance_agent.domain.negotiation import (
    DecisionValue,
    ReviewCode,
    ReviewReason,
    TerminalStatus,
    TimeInterval,
)
from maintenance_agent.domain.scheduling import (
    common_windows,
    create_candidates,
    overlaps,
    urgency_comparison,
)
from maintenance_agent.domain.work_orders import Urgency


def interval(start: int, end: int) -> TimeInterval:
    origin = datetime(2026, 10, 12, tzinfo=timezone.utc)
    return TimeInterval(origin + timedelta(hours=start), origin + timedelta(hours=end))


def test_interval_is_aware_and_half_open() -> None:
    with pytest.raises(ValueError):
        TimeInterval(datetime(2026, 10, 12), datetime(2026, 10, 13))
    assert not overlaps(interval(9, 11), interval(11, 13))
    assert overlaps(interval(9, 11), interval(10, 12))


def test_merge_then_slice_and_keep_distinct_overlapping_starts() -> None:
    base = interval(9, 13)
    merged = create_candidates("WO-1", (interval(9, 11), interval(11, 13)), 1)
    assert [item.interval.start for item in merged] == [base.start, base.start + timedelta(hours=2)]
    offset = create_candidates("WO-1", (interval(10, 14),), 2)
    assert len(offset) == 2
    assert offset[0].interval.start != merged[0].interval.start
    assert overlaps(offset[0].interval, merged[0].interval)


RANKS = active_rules().urgency_rank


def test_common_window_includes_two_hour_intersection_and_urgency_order() -> None:
    assert common_windows((interval(9, 13),), (interval(10, 12),)) == (interval(10, 12),)
    assert urgency_comparison(Urgency.CRITICAL, Urgency.HIGH, RANKS) > 0
    assert urgency_comparison(Urgency.HIGH, Urgency.HIGH, RANKS) == 0
    assert urgency_comparison(Urgency.LOW, Urgency.MEDIUM, RANKS) < 0


def test_terminal_enum_and_review_reason_are_closed_and_safe() -> None:
    assert {status.value for status in TerminalStatus} == {"scheduled", "requires_review"}
    reason = ReviewReason(ReviewCode.NO_RESPONSE, "No response\nfrom tenant")
    assert reason.render_line() == (
        r"No response\nfrom tenant Evidence: tenant requested intervals unknown."
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Sí, por favor.", DecisionValue.YES),
        ("yes", DecisionValue.YES),
        ("no me viene bien", DecisionValue.NO),
        ("That does not work.", DecisionValue.NO),
        ("lunes de 12 a 14", None),
        ("sí, pero solo si cambia la hora", None),
    ],
)
def test_explicit_decision_is_deterministic_and_conservative(message, expected) -> None:
    assert interpret_explicit_decision(message) is expected
