"""Single-lock process-local authority for the shared visit schedule."""

import asyncio
from collections.abc import Mapping

from maintenance_agent.application.scheduling import (
    Appointment,
    CandidateAvailability,
    CandidateInspection,
    Hold,
    ScheduleBlocker,
    ScheduleSnapshot,
)
from maintenance_agent.business_rules import active_rules
from maintenance_agent.domain.negotiation import (
    AvailabilityEvidence,
    DecisionValue,
    ParticipantDecision,
    ParticipantRole,
    ReviewReason,
    VisitCandidate,
)
from maintenance_agent.domain.scheduling import (
    common_windows,
    create_candidates,
    overlaps,
    urgency_comparison,
)
from maintenance_agent.domain.work_orders import Urgency


class InMemoryScheduleAuthority:
    """Serialize agenda reads and state transitions; never expose mutable internals."""

    def __init__(self, urgency_ranks: Mapping[str, int] | None = None) -> None:
        self._urgency_ranks = (
            urgency_ranks if urgency_ranks is not None else active_rules().urgency_rank
        )
        self._lock = asyncio.Lock()
        self._version = 0
        self._holds: dict[str, Hold] = {}
        self._appointments: dict[str, Appointment] = {}
        self._evidence: dict[tuple[str, str], AvailabilityEvidence] = {}
        self._terminal: dict[str, tuple[str, ReviewReason | None]] = {}

    async def snapshot(self) -> ScheduleSnapshot:
        async with self._lock:
            return ScheduleSnapshot(
                self._version,
                tuple(self._holds.values()),
                tuple(self._appointments.values()),
                tuple(self._evidence.values()),
            )

    async def inspect_candidates(
        self, candidates: tuple[VisitCandidate, ...], urgency: Urgency
    ) -> tuple[CandidateInspection, ...]:
        async with self._lock:
            results = []
            for candidate in candidates:
                blockers: list[ScheduleBlocker] = []
                preemptible = True
                for appointment in self._appointments.values():
                    if overlaps(candidate.interval, appointment.interval):
                        blockers.append(
                            ScheduleBlocker(
                                appointment.work_order_id, appointment.interval, None, True
                            )
                        )
                        preemptible = False
                for hold in self._holds.values():
                    if overlaps(candidate.interval, hold.interval):
                        blockers.append(
                            ScheduleBlocker(hold.work_order_id, hold.interval, hold.urgency, False)
                        )
                        if (
                            hold.work_order_id == candidate.work_order_id
                            or urgency_comparison(urgency, hold.urgency, self._urgency_ranks) <= 0
                        ):
                            preemptible = False
                availability = (
                    CandidateAvailability.FREE
                    if not blockers
                    else CandidateAvailability.PREEMPTIBLE
                    if preemptible
                    else CandidateAvailability.BLOCKED
                )
                results.append(CandidateInspection(candidate, availability, tuple(blockers)))
            return tuple(results)

    async def known_eligible_candidates(
        self, work_order_id: str, urgency: Urgency
    ) -> tuple[VisitCandidate, ...]:
        """Return earliest already evidenced, currently eligible full visits."""
        async with self._lock:
            tenant = self._evidence.get((work_order_id, "tenant"))
            handyman = self._evidence.get((work_order_id, "handyman"))
            if (
                tenant is None
                or handyman is None
                or not tenant.complete
                or not handyman.complete
                or tenant.disputed
                or handyman.disputed
            ):
                return ()
            windows = common_windows(tenant.intervals, handyman.intervals)
            candidates = create_candidates(work_order_id, windows, tenant.revision)
            eligible: list[VisitCandidate] = []
            for candidate in candidates:
                if any(
                    overlaps(candidate.interval, appointment.interval)
                    for appointment in self._appointments.values()
                ):
                    continue
                conflicts = [
                    hold
                    for hold in self._holds.values()
                    if overlaps(candidate.interval, hold.interval)
                ]
                if any(
                    hold.work_order_id == work_order_id
                    or urgency_comparison(urgency, hold.urgency, self._urgency_ranks) <= 0
                    for hold in conflicts
                ):
                    continue
                eligible.append(candidate)
            return tuple(sorted(eligible, key=lambda item: (item.interval.start, item.slot_id)))

    async def acquire_or_transfer_hold(
        self, candidate: VisitCandidate, urgency: Urgency, proposal_id: str, proposal_version: int
    ) -> tuple[bool, tuple[str, ...]]:
        async with self._lock:
            if candidate.work_order_id in self._terminal:
                return False, ()
            if any(
                overlaps(candidate.interval, appointment.interval)
                for appointment in self._appointments.values()
            ):
                return False, ()
            conflicts = [
                hold for hold in self._holds.values() if overlaps(candidate.interval, hold.interval)
            ]
            if any(
                hold.work_order_id == candidate.work_order_id
                or urgency_comparison(urgency, hold.urgency, self._urgency_ranks) <= 0
                for hold in conflicts
            ):
                return False, ()
            displaced = tuple(sorted({hold.work_order_id for hold in conflicts}))
            for hold in conflicts:
                self._holds.pop(hold.work_order_id, None)
            self._holds[candidate.work_order_id] = Hold(
                hold_id=f"{candidate.work_order_id}:{proposal_id}:{proposal_version}",
                work_order_id=candidate.work_order_id,
                interval=candidate.interval,
                urgency=urgency,
                proposal_id=proposal_id,
                proposal_version=proposal_version,
            )
            self._version += 1
            return True, displaced

    async def apply_availability_change(self, evidence: AvailabilityEvidence) -> int:
        async with self._lock:
            key = (evidence.work_order_id, evidence.role.value)
            previous = self._evidence.get(key)
            if previous is None or evidence.revision > previous.revision:
                self._evidence[key] = evidence
                self._version += 1
            return self._version

    async def close_review(self, work_order_id: str, reason: ReviewReason) -> bool:
        async with self._lock:
            if work_order_id in self._terminal:
                return False
            self._terminal[work_order_id] = ("requires_review", reason)
            self._holds.pop(work_order_id, None)
            self._version += 1
            return True

    async def commit_appointment(
        self,
        candidate: VisitCandidate,
        proposal_id: str,
        proposal_version: int,
        acceptances: tuple[ParticipantDecision, ParticipantDecision],
    ) -> Appointment | None:
        async with self._lock:
            work_order_id = candidate.work_order_id
            if work_order_id in self._terminal or len(acceptances) != 2:
                return None
            if (
                {item.role for item in acceptances}
                != {ParticipantRole.TENANT, ParticipantRole.HANDYMAN}
                or any(
                    item.decision is not DecisionValue.YES
                    or item.clarification_required
                    or item.proposal_id != proposal_id
                    or item.proposal_version != proposal_version
                    for item in acceptances
                )
                or acceptances[0].question_id == acceptances[1].question_id
            ):
                return None
            current_hold = self._holds.get(work_order_id)
            if (
                current_hold is None
                or current_hold.proposal_id != proposal_id
                or current_hold.proposal_version != proposal_version
                or current_hold.interval != candidate.interval
            ):
                return None
            if any(
                other.work_order_id != work_order_id
                and overlaps(candidate.interval, other.interval)
                for other in self._appointments.values()
            ):
                return None
            if any(
                hold.work_order_id != work_order_id and overlaps(candidate.interval, hold.interval)
                for hold in self._holds.values()
            ):
                return None
            self._version += 1
            appointment = Appointment(
                appointment_id=f"{work_order_id}:{proposal_id}:{proposal_version}",
                work_order_id=work_order_id,
                interval=candidate.interval,
                proposal_id=proposal_id,
                proposal_version=proposal_version,
                acceptances=tuple(item.question_id for item in acceptances),
                schedule_version=self._version,
            )
            self._appointments[work_order_id] = appointment
            self._terminal[work_order_id] = ("scheduled", None)
            self._holds.pop(work_order_id, None)
            return appointment

    async def release_hold(self, work_order_id: str, proposal_id: str) -> bool:
        async with self._lock:
            hold = self._holds.get(work_order_id)
            if (
                hold is None
                or hold.proposal_id != proposal_id
                or work_order_id in self._appointments
            ):
                return False
            self._holds.pop(work_order_id)
            self._version += 1
            return True

    async def terminal_result(self, work_order_id: str) -> tuple[str, ReviewReason | None] | None:
        async with self._lock:
            return self._terminal.get(work_order_id)
