"""Immutable records and protocol types for visit negotiation."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo


class ParticipantRole(StrEnum):
    TENANT = "tenant"
    HANDYMAN = "handyman"


class TerminalStatus(StrEnum):
    SCHEDULED = "scheduled"
    REQUIRES_REVIEW = "requires_review"


class GraphCursor(StrEnum):
    START = "start"
    TENANT_AVAILABILITY = "tenant_availability"
    TENANT_ALTERNATIVES = "tenant_alternatives"
    RELATIVE_DATE_CONFIRMATION = "relative_date_confirmation"
    HANDYMAN_AVAILABILITY = "handyman_availability"
    TENANT_CONFIRMATION = "tenant_confirmation"
    HANDYMAN_CONFIRMATION = "handyman_confirmation"
    AVAILABILITY_CHANGE = "availability_change"
    HUMAN_SCHEDULING = "human_scheduling"
    DISPLACED_ALTERNATIVE = "displaced_alternative"
    HANDLE_DISPLACED_HOLD = "handle_displaced_hold"
    SLOT_SUGGESTION = "slot_suggestion"
    SLOT_FALLBACK = "slot_fallback"


class PendingAction(StrEnum):
    TENANT_AVAILABILITY = "tenant_availability"
    TENANT_ALTERNATIVES = "tenant_alternatives"
    DISPLACED_ALTERNATIVE = "displaced_alternative"
    RELATIVE_DATE_CONFIRMATION = "relative_date_confirmation"
    HANDYMAN_AVAILABILITY = "handyman_availability"
    TENANT_CONFIRMATION = "tenant_confirmation"
    HANDYMAN_CONFIRMATION = "handyman_confirmation"
    AVAILABILITY_CHANGE = "availability_change"
    HUMAN_SCHEDULING = "human_scheduling"
    SLOT_SUGGESTION = "slot_suggestion"
    SLOT_FALLBACK = "slot_fallback"


class DecisionValue(StrEnum):
    YES = "yes"
    NO = "no"


class ReviewCode(StrEnum):
    NO_RESPONSE = "no_response"
    NO_COMMON_AVAILABILITY = "no_common_availability"
    NO_ELIGIBLE_SLOT = "no_eligible_slot"


@dataclass(frozen=True, slots=True)
class TimeInterval:
    """A UTC-normalized, semi-open interval."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        from datetime import timezone

        if (
            self.start.tzinfo is None
            or self.end.tzinfo is None
            or self.start.utcoffset() is None
            or self.end.utcoffset() is None
        ):
            raise ValueError("Intervals must be timezone-aware.")
        start = self.start.astimezone(timezone.utc)
        end = self.end.astimezone(timezone.utc)
        if end <= start:
            raise ValueError("Interval end must be after its start.")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)


@dataclass(frozen=True, slots=True)
class AvailabilityEvidence:
    work_order_id: str
    role: ParticipantRole
    intervals: tuple[TimeInterval, ...]
    revision: int
    complete: bool = True
    disputed: bool = False
    source_question_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "intervals", tuple(self.intervals))


@dataclass(frozen=True, slots=True)
class VisitCandidate:
    slot_id: str
    work_order_id: str
    interval: TimeInterval
    source_revision: int
    counterproposal: bool = False

    def __post_init__(self) -> None:
        if self.interval.end - self.interval.start != timedelta(hours=2):
            raise ValueError("Visit candidates must be exactly two hours.")


@dataclass(frozen=True, slots=True)
class PendingQuestion:
    question_id: str
    role: ParticipantRole
    action: PendingAction
    workflow_version: int
    schedule_version: int
    proposal_id: str | None = None
    proposal_version: int | None = None


@dataclass(frozen=True, slots=True)
class Proposal:
    proposal_id: str
    proposal_version: int
    candidate: VisitCandidate
    tenant_revision: int
    handyman_revision: int
    schedule_version: int
    state: str = "offered"


@dataclass(frozen=True, slots=True)
class ParticipantDecision:
    question_id: str
    role: ParticipantRole
    proposal_id: str
    proposal_version: int
    decision: DecisionValue | None
    clarification_required: bool = False

    def __post_init__(self) -> None:
        if self.clarification_required and self.decision is not None:
            raise ValueError("A clarification-required decision cannot contain yes or no.")


@dataclass(frozen=True, slots=True)
class ReviewReason:
    reason_code: ReviewCode
    detail: str
    silent_role: ParticipantRole | None = None
    current_node: str | None = None
    question_id: str | None = None
    tenant_windows: tuple[TimeInterval, ...] = ()
    handyman_windows: tuple[TimeInterval, ...] | None = None
    blockers: tuple[str, ...] = ()
    evidence: tuple[tuple[str, str], ...] = ()
    timezone_name: str = "Europe/Madrid"

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_windows", tuple(self.tenant_windows))
        if self.handyman_windows is not None:
            object.__setattr__(self, "handyman_windows", tuple(self.handyman_windows))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "evidence", tuple(self.evidence))

    def render_line(self) -> str:
        """Serialize deterministic single-line English evidence safely."""
        safe = self.detail.replace("\r", r"\r").replace("\n", r"\n")
        parts = [" ".join(safe.split())]
        zone = ZoneInfo(self.timezone_name)

        def render(windows: tuple[TimeInterval, ...]) -> str:
            return "; ".join(
                f"{item.start.astimezone(zone).strftime('%Y-%m-%d %H:%M')}–"
                f"{item.end.astimezone(zone).strftime('%Y-%m-%d %H:%M')} {self.timezone_name}"
                for item in windows
            )

        if self.reason_code is ReviewCode.NO_RESPONSE:
            context = []
            if self.silent_role is not None:
                context.append(f"silent role {self.silent_role.value}")
            if self.current_node:
                context.append(f"current node {self.current_node}")
            if self.question_id:
                context.append(f"question {self.question_id}")
            context.append(
                f"tenant requested {render(self.tenant_windows)}"
                if self.tenant_windows
                else "tenant requested intervals unknown"
            )
            parts.append("Evidence: " + "; ".join(context) + ".")
        elif self.reason_code is ReviewCode.NO_COMMON_AVAILABILITY:
            parts.append("Tenant availability: " + (render(self.tenant_windows) or "unknown") + ".")
            parts.append(
                "Handyman availability: "
                + (
                    render(self.handyman_windows)
                    if self.handyman_windows is not None
                    else "unknown"
                )
                + "."
            )
        elif self.reason_code is ReviewCode.NO_ELIGIBLE_SLOT:
            parts.append("Tenant requested: " + (render(self.tenant_windows) or "unknown") + ".")
            parts.append(
                "Agenda blockers: "
                + ("; ".join(self.blockers) or "recorded blockers unavailable")
                + "."
            )
        for key, value in self.evidence:
            escaped = value.replace("\r", r"\r").replace("\n", r"\n")
            parts.append(f"{key}: {escaped}")
        return " ".join(parts)


@dataclass(frozen=True, slots=True)
class WorkOrderNegotiation:
    work_order_id: str
    workflow_version: int = 0
    terminal_status: TerminalStatus | None = None
    pending_question: PendingQuestion | None = None
    tenant_language: str = "undetermined"
    tenant_evidence: AvailabilityEvidence | None = None
    handyman_evidence: AvailabilityEvidence | None = None
    candidates: tuple[VisitCandidate, ...] = ()
    proposal: Proposal | None = None
    decisions: tuple[ParticipantDecision, ...] = ()
    review_reason: ReviewReason | None = None
    finalization_pending: bool = False
    confirmations_sent: frozenset[ParticipantRole] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "decisions", tuple(self.decisions))
        object.__setattr__(self, "confirmations_sent", frozenset(self.confirmations_sent))
        if self.terminal_status is TerminalStatus.REQUIRES_REVIEW and self.review_reason is None:
            raise ValueError("requires_review must carry a structured review reason.")
        if (
            self.review_reason is not None
            and self.terminal_status is not TerminalStatus.REQUIRES_REVIEW
        ):
            raise ValueError("A review reason is valid only for requires_review.")
