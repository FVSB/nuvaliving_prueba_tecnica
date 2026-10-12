"""Schedule authority contract and immutable inspection results."""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from maintenance_agent.domain.negotiation import (
    AvailabilityEvidence,
    ParticipantDecision,
    ReviewReason,
    TimeInterval,
    VisitCandidate,
)
from maintenance_agent.domain.work_orders import Urgency

if TYPE_CHECKING:
    from maintenance_agent.infrastructure.in_memory_schedule import ScheduleSnapshot


class CandidateAvailability(StrEnum):
    FREE = "free"
    PREEMPTIBLE = "preemptible"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ScheduleBlocker:
    work_order_id: str
    interval: TimeInterval
    urgency: Urgency | None
    confirmed: bool


@dataclass(frozen=True, slots=True)
class CandidateInspection:
    candidate: VisitCandidate
    availability: CandidateAvailability
    blockers: tuple[ScheduleBlocker, ...] = ()


@dataclass(frozen=True, slots=True)
class Hold:
    hold_id: str
    work_order_id: str
    interval: TimeInterval
    urgency: Urgency
    proposal_id: str
    proposal_version: int


@dataclass(frozen=True, slots=True)
class Appointment:
    appointment_id: str
    work_order_id: str
    interval: TimeInterval
    proposal_id: str
    proposal_version: int
    acceptances: tuple[str, str]
    schedule_version: int


@dataclass(frozen=True, slots=True)
class ScheduleSnapshot:
    version: int
    holds: tuple[Hold, ...]
    appointments: tuple[Appointment, ...]
    evidence: tuple[AvailabilityEvidence, ...]


class ScheduleAuthority(Protocol):
    async def snapshot(self) -> ScheduleSnapshot: ...

    async def inspect_candidates(
        self, candidates: tuple[VisitCandidate, ...], urgency: Urgency
    ) -> tuple[CandidateInspection, ...]: ...

    async def acquire_or_transfer_hold(
        self, candidate: VisitCandidate, urgency: Urgency, proposal_id: str, proposal_version: int
    ) -> tuple[bool, tuple[str, ...]]: ...

    async def close_review(self, work_order_id: str, reason: ReviewReason) -> bool: ...

    async def release_hold(self, work_order_id: str, proposal_id: str) -> bool: ...

    async def apply_availability_change(self, evidence: AvailabilityEvidence) -> int: ...

    async def commit_appointment(
        self,
        candidate: VisitCandidate,
        proposal_id: str,
        proposal_version: int,
        acceptances: tuple[ParticipantDecision, ParticipantDecision],
    ) -> Appointment | None: ...
