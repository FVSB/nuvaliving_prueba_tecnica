"""Shared builders for Feature 005 slot-suggestion tests."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from maintenance_agent.application.conversation import (
    AvailabilityInterpretation,
    MessageClass,
)
from maintenance_agent.application.scheduling import Appointment, ScheduleSnapshot
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.negotiation import TimeInterval
from maintenance_agent.domain.work_orders import Urgency, WorkOrder
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority

MADRID = ZoneInfo("Europe/Madrid")
NOW = datetime(2026, 10, 12, 8, 0, tzinfo=MADRID)

VAGUE = AvailabilityInterpretation((), False, True, classification=MessageClass.VAGUE_DATE_REQUEST)


def work_order(order_id: str = "WO-S1") -> WorkOrder:
    return WorkOrder(
        work_order_id=order_id,
        work_order="Leak",
        address="Calle Sol 4",
        description="Fuga de agua",
        reported_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
        urgency=Urgency.MEDIUM,
    )


def appointment_at(hour: int, day: int = 12) -> Appointment:
    start = datetime(2026, 10, day, hour, tzinfo=MADRID)
    end = datetime(2026, 10, day, hour + 2, tzinfo=MADRID)
    return Appointment("APP", "WO-X", TimeInterval(start, end), "P", 1, ("a", "b"), 1)


def snapshot_with(*appointments: Appointment) -> ScheduleSnapshot:
    return ScheduleSnapshot(1, (), tuple(appointments), ())


class StubAgenda(InMemoryScheduleAuthority):
    def __init__(self, *appointments: Appointment) -> None:
        super().__init__()
        self._stub = snapshot_with(*appointments)

    async def snapshot(self) -> ScheduleSnapshot:
        return self._stub


async def started(workflow: NegotiationWorkflow, lang: LanguageCode = LanguageCode.SPANISH):
    return await workflow.start(work_order(), LanguageRecognitionResult(language_code=lang))
