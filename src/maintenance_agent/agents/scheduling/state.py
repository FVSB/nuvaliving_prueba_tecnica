"""Typed state for the scheduling graph."""

from typing import NotRequired, TypedDict

from maintenance_agent.application.messages import InboundMessage, OutboundMessage, TerminalFrame
from maintenance_agent.domain.languages import LanguageRecognitionResult
from maintenance_agent.domain.negotiation import (
    AvailabilityEvidence,
    GraphCursor,
    ParticipantDecision,
    ParticipantRole,
    PendingQuestion,
    Proposal,
    ReviewReason,
    TerminalStatus,
    TimeInterval,
    VisitCandidate,
)
from maintenance_agent.domain.work_orders import WorkOrder


class SchedulingState(TypedDict):
    """State shared by the first scheduling-graph nodes."""

    work_order: WorkOrder
    language_recognition: NotRequired[LanguageRecognitionResult]
    outbound_message: NotRequired[OutboundMessage]
    workflow_version: NotRequired[int]
    terminal_status: NotRequired[TerminalStatus | None]
    pending_question: NotRequired[PendingQuestion | None]
    graph_cursor: NotRequired[GraphCursor]
    tenant_language: NotRequired[str]
    tenant_evidence: NotRequired[AvailabilityEvidence | None]
    handyman_evidence: NotRequired[AvailabilityEvidence | None]
    candidates: NotRequired[tuple[VisitCandidate, ...]]
    proposal: NotRequired[Proposal | None]
    review_reason: NotRequired[ReviewReason | None]
    finalization_pending: NotRequired[bool]
    inbound_message: NotRequired[InboundMessage]
    terminal_frame: NotRequired[TerminalFrame | None]
    resume_finalization: NotRequired[bool]
    decisions: NotRequired[tuple[ParticipantDecision, ...]]
    confirmations_sent: NotRequired[frozenset[ParticipantRole]]
    relative_date_intervals: NotRequired[tuple[TimeInterval, ...]]
    all_tenant_candidates: NotRequired[tuple[VisitCandidate, ...]]
    common_candidates: NotRequired[tuple[VisitCandidate, ...]]
    displaced_work_orders: NotRequired[tuple[str, ...]]
    agenda_blockers: NotRequired[tuple[str, ...]]
    disputed_availability: NotRequired[dict | None]
    displaced_hold_event: NotRequired[bool]
    displaced_candidate: NotRequired[VisitCandidate | None]
