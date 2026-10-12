"""Pure interval and urgency rules for the shared handyman agenda."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from zoneinfo import ZoneInfo

from maintenance_agent.domain.negotiation import TimeInterval, VisitCandidate
from maintenance_agent.domain.work_orders import Urgency

VISIT_DURATION = timedelta(hours=2)
_URGENCY_RANK = {
    Urgency.LOW: 0,
    Urgency.MEDIUM: 1,
    Urgency.HIGH: 2,
    Urgency.CRITICAL: 3,
}


@dataclass(frozen=True, slots=True)
class SlotFeasibility:
    """Whether a proposed visit can be offered, with the limits that reject it."""

    feasible: bool
    reasons: tuple[str, ...]


def check_visit_feasibility(
    interval: TimeInterval,
    declared_availability: tuple[TimeInterval, ...] = (),
    incompatible_occupied: tuple[TimeInterval, ...] = (),
) -> SlotFeasibility:
    """Check a visit against the existing limits: two hours, inside the declared
    availability, and free of incompatible confirmed or retained occupancy."""
    reasons: list[str] = []
    if interval.end - interval.start != VISIT_DURATION:
        reasons.append("visit_must_last_two_hours")
    if declared_availability and not any(
        window.start <= interval.start and interval.end <= window.end
        for window in declared_availability
    ):
        reasons.append("outside_declared_availability")
    reasons.extend(
        f"overlaps_occupied:{occupied.start.isoformat()}/{occupied.end.isoformat()}"
        for occupied in incompatible_occupied
        if overlaps(interval, occupied)
    )
    return SlotFeasibility(not reasons, tuple(reasons))


def normalize_interval(start: datetime, end: datetime) -> TimeInterval:
    return TimeInterval(start, end)


def visit_interval_from_start(start: datetime, timezone_name: str) -> TimeInterval:
    """Complete a tenant-supplied visit start using the fixed two-hour duration."""
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("A visit start must include a UTC offset.")
    zone = ZoneInfo(timezone_name)
    local_start = start.astimezone(zone)
    utc_end = local_start.astimezone(timezone.utc) + VISIT_DURATION
    return TimeInterval(local_start, utc_end.astimezone(zone))


def overlaps(left: TimeInterval, right: TimeInterval) -> bool:
    return left.start < right.end and right.start < left.end


def merge_intervals(
    intervals: tuple[TimeInterval, ...] | list[TimeInterval],
) -> tuple[TimeInterval, ...]:
    ordered = sorted(intervals, key=lambda interval: (interval.start, interval.end))
    merged: list[TimeInterval] = []
    for interval in ordered:
        if merged and interval.start <= merged[-1].end:
            merged[-1] = TimeInterval(merged[-1].start, max(merged[-1].end, interval.end))
        else:
            merged.append(interval)
    return tuple(merged)


def stable_slot_id(
    work_order_id: str, start: datetime, duration: timedelta = VISIT_DURATION
) -> str:
    payload = (
        f"{work_order_id}|{start.astimezone(timezone.utc).isoformat()}|{duration.total_seconds()}"
    )
    return sha256(payload.encode()).hexdigest()[:16]


def create_candidates(
    work_order_id: str,
    intervals: tuple[TimeInterval, ...] | list[TimeInterval],
    revision: int,
) -> tuple[VisitCandidate, ...]:
    candidates: dict[str, VisitCandidate] = {}
    for window in merge_intervals(intervals):
        start = window.start
        while start + VISIT_DURATION <= window.end:
            slot_id = stable_slot_id(work_order_id, start)
            candidates.setdefault(
                slot_id,
                VisitCandidate(
                    slot_id, work_order_id, TimeInterval(start, start + VISIT_DURATION), revision
                ),
            )
            start += VISIT_DURATION
    return tuple(sorted(candidates.values(), key=lambda item: (item.interval.start, item.slot_id)))


def common_windows(
    tenant_windows: tuple[TimeInterval, ...], handyman_windows: tuple[TimeInterval, ...]
) -> tuple[TimeInterval, ...]:
    intersections = []
    for tenant in tenant_windows:
        for handyman in handyman_windows:
            start, end = max(tenant.start, handyman.start), min(tenant.end, handyman.end)
            if end - start >= VISIT_DURATION:
                intersections.append(TimeInterval(start, end))
    return merge_intervals(intersections)


def urgency_comparison(requester: Urgency, incumbent: Urgency) -> int:
    """Return positive only when the requester strictly outranks the incumbent."""
    return _URGENCY_RANK[requester] - _URGENCY_RANK[incumbent]


def local_interval(interval: TimeInterval, timezone_name: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    return interval.start.astimezone(zone), interval.end.astimezone(zone)
