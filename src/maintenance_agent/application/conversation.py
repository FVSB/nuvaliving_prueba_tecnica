"""Typed conversation boundaries used by the negotiation workflow."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from maintenance_agent.application.messages import OutboundMessage
from maintenance_agent.domain.negotiation import (
    DecisionValue,
    ParticipantRole,
    TimeInterval,
)


class MessageClass(StrEnum):
    """Routing verdict for an inbound participant message in the availability phase."""

    EXPLICIT_INTERVALS = "explicit_intervals"
    VAGUE_DATE_REQUEST = "vague_date_request"
    DECISION = "decision"
    UNCLASSIFIED = "unclassified"


class PartOfDay(StrEnum):
    """Coarse day part named by a vague request; morning ends at 12:00 local."""

    NONE = "none"
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class AmbiguityReason(StrEnum):
    """Why a vague date request could not become explicit intervals."""

    UNSPECIFIED_TIME = "unspecified_time"
    UNSPECIFIED_DAY = "unspecified_day"
    AMBIGUOUS_AM_PM = "ambiguous_am_pm"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class DecisionInterpretation:
    """Conservative yes/no reading of an explicit reply; never inferred."""

    decision: DecisionValue | None
    clarification_required: bool


class MessageInterpreter(Protocol):
    async def interpret_availability(
        self,
        text: str,
        role: ParticipantRole,
        reference_time: datetime,
        timezone_name: str,
    ) -> "AvailabilityInterpretation": ...


class MessageComposer(Protocol):
    async def compose(self, intent: str, language: str, facts: dict[str, str]) -> str: ...


class ConversationHandler(MessageInterpreter, MessageComposer, Protocol):
    """Combined injected port used by the negotiation workflow."""

    async def compose_slot_reply(
        self, language: str, facts: dict[str, str]
    ) -> tuple[str, str]:
        """Return (intro, ask) prose lines around the deterministic slot table."""

    async def validate_slot_reply(self, reply: str, facts: dict[str, str]) -> "ValidationVerdict":
        """Validate a drafted slot-suggestion reply before it is sent."""


class ConversationOutbound(Protocol):
    async def send(self, message: OutboundMessage) -> None: ...


@dataclass(frozen=True, slots=True)
class AvailabilityInterpretation:
    intervals: tuple[TimeInterval, ...]
    complete: bool
    clarification_required: bool
    suggested_intervals: tuple[TimeInterval, ...] = ()
    date_confirmation_required: bool = False
    clarification: str | None = None
    weekday_is_today: bool = False
    classification: MessageClass = MessageClass.UNCLASSIFIED
    date_from: str | None = None
    date_to: str | None = None
    part_of_day: PartOfDay = PartOfDay.NONE
    ambiguity_reason: AmbiguityReason = AmbiguityReason.OTHER


@dataclass(frozen=True, slots=True)
class ValidationVerdict:
    """Structured pre-send validation result for a drafted slot-suggestion reply."""

    valid: bool
    feedback: str | None = None
    diagnostic: str | None = None


class SafeFallbackConversationHandler:
    """Remain safe without credentials: request clarification instead of inferring evidence."""

    async def interpret_availability(
        self,
        text: str,
        role: ParticipantRole,
        reference_time: datetime,
        timezone_name: str,
    ) -> AvailabilityInterpretation:
        return AvailabilityInterpretation((), False, True)

    async def compose(self, intent: str, language: str, facts: dict[str, str]) -> str:
        return (
            "We can help with this maintenance request. Please share the dates and times "
            "when you are available. / "
            "Podemos ayudarle con esta reparación. Indique las fechas y horas "
            "en que está disponible."
        )

    async def compose_slot_reply(
        self, language: str, facts: dict[str, str]
    ) -> tuple[str, str]:
        return (
            "We can help with this maintenance request.",
            "Please share the dates and times when you are available.",
        )

    async def validate_slot_reply(
        self, reply: str, facts: dict[str, str]
    ) -> ValidationVerdict:
        return ValidationVerdict(True, None)
