import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from maintenance_agent.domain.negotiation import TimeInterval, VisitCandidate
from maintenance_agent.domain.work_orders import Urgency
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority


def candidate(order: str, start: int) -> VisitCandidate:
    at = datetime(2026, 10, 12, start, tzinfo=timezone.utc)
    return VisitCandidate(order, order, TimeInterval(at, at + timedelta(hours=2)), 1)


@pytest.mark.asyncio
async def test_concurrent_overlapping_acquisitions_have_single_winner() -> None:
    agenda = InMemoryScheduleAuthority()
    outcomes = await asyncio.gather(
        agenda.acquire_or_transfer_hold(candidate("WO-A", 9), Urgency.HIGH, "a", 1),
        agenda.acquire_or_transfer_hold(candidate("WO-B", 10), Urgency.HIGH, "b", 1),
    )
    assert sum(int(accepted) for accepted, _ in outcomes) == 1
    snapshot = await agenda.snapshot()
    assert len(snapshot.holds) == 1


@pytest.mark.asyncio
async def test_snapshot_is_immutable_and_does_not_hold_lock_for_external_wait() -> None:
    agenda = InMemoryScheduleAuthority()
    await agenda.acquire_or_transfer_hold(candidate("WO-A", 9), Urgency.LOW, "a", 1)
    snapshot = await agenda.snapshot()
    assert isinstance(snapshot.holds, tuple)
    await asyncio.wait_for(agenda.inspect_candidates((candidate("WO-B", 12),), Urgency.LOW), 0.1)
