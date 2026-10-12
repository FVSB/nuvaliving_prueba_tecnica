from datetime import datetime, timedelta, timezone

import pytest

from maintenance_agent.domain.negotiation import (
    DecisionValue,
    ParticipantDecision,
    ParticipantRole,
    ReviewCode,
    ReviewReason,
    TimeInterval,
    VisitCandidate,
)
from maintenance_agent.domain.work_orders import Urgency
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority


def acceptances(proposal: str, version: int = 1, suffix: str = "") -> tuple:
    return (
        ParticipantDecision(
            f"q-tenant{suffix}", ParticipantRole.TENANT, proposal, version, DecisionValue.YES
        ),
        ParticipantDecision(
            f"q-handyman{suffix}", ParticipantRole.HANDYMAN, proposal, version, DecisionValue.YES
        ),
    )


def candidate(order: str, start: int) -> VisitCandidate:
    at = datetime(2026, 10, 12, start, tzinfo=timezone.utc)
    return VisitCandidate(order + str(start), order, TimeInterval(at, at + timedelta(hours=2)), 1)


@pytest.mark.asyncio
async def test_atomic_multi_hold_transfer_conflict_and_confirmed_protection() -> None:
    agenda = InMemoryScheduleAuthority()
    assert (await agenda.acquire_or_transfer_hold(candidate("WO-L1", 9), Urgency.LOW, "p1", 1))[0]
    assert (await agenda.acquire_or_transfer_hold(candidate("WO-L2", 11), Urgency.MEDIUM, "p2", 1))[
        0
    ]
    ok, displaced = await agenda.acquire_or_transfer_hold(
        candidate("WO-H", 10), Urgency.HIGH, "p3", 1
    )
    assert ok is True
    assert displaced == ("WO-L1", "WO-L2")
    assert await agenda.commit_appointment(candidate("WO-H", 10), "p3", 1, acceptances("p3"))
    assert await agenda.acquire_or_transfer_hold(
        candidate("WO-C", 11), Urgency.CRITICAL, "p4", 1
    ) == (False, ())


@pytest.mark.asyncio
async def test_review_and_commit_are_mutually_exclusive_and_snapshot_detached() -> None:
    agenda = InMemoryScheduleAuthority()
    snapshot = await agenda.snapshot()
    assert snapshot.holds == ()
    work = candidate("WO-R", 9)
    assert (await agenda.acquire_or_transfer_hold(work, Urgency.HIGH, "p", 1))[0]
    committed, reviewed = await __import__("asyncio").gather(
        agenda.commit_appointment(work, "p", 1, acceptances("p", suffix="-q")),
        agenda.close_review("WO-R", ReviewReason(ReviewCode.NO_RESPONSE, "timeout")),
    )
    assert (committed is not None) != reviewed
    result = await agenda.terminal_result("WO-R")
    assert result is not None
    assert len((await agenda.snapshot()).appointments) == int(committed is not None)


def test_visit_interval_from_start_completes_two_hours() -> None:
    from zoneinfo import ZoneInfo

    from maintenance_agent.domain.scheduling import visit_interval_from_start

    start = datetime(2026, 10, 13, 18, tzinfo=ZoneInfo("Europe/Madrid"))
    interval = visit_interval_from_start(start, "Europe/Madrid")
    assert interval.start == start
    assert interval.end - interval.start == timedelta(hours=2)
    assert interval.end == datetime(2026, 10, 13, 20, tzinfo=ZoneInfo("Europe/Madrid"))


def test_check_visit_feasibility_reports_each_broken_limit() -> None:
    from maintenance_agent.domain.scheduling import check_visit_feasibility

    day = datetime(2026, 10, 20, tzinfo=timezone.utc)
    declared = (TimeInterval(day, day + timedelta(hours=8)),)
    occupied = (TimeInterval(day + timedelta(hours=4), day + timedelta(hours=6)),)

    ok = check_visit_feasibility(TimeInterval(day, day + timedelta(hours=2)), declared, occupied)
    assert ok.feasible is True and ok.reasons == ()

    wrong_duration = check_visit_feasibility(
        TimeInterval(day, day + timedelta(hours=3)), declared, ()
    )
    assert wrong_duration.feasible is False
    assert wrong_duration.reasons == ("visit_must_last_two_hours",)

    outside = check_visit_feasibility(
        TimeInterval(day + timedelta(hours=9), day + timedelta(hours=11)), declared, ()
    )
    assert outside.feasible is False
    assert outside.reasons == ("outside_declared_availability",)

    overlapping = check_visit_feasibility(
        TimeInterval(day + timedelta(hours=5), day + timedelta(hours=7)), declared, occupied
    )
    assert overlapping.feasible is False
    assert overlapping.reasons[0].startswith("overlaps_occupied:")
