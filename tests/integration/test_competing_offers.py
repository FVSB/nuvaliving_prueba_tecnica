"""Error 16: the same slot may be offered to two orders before any hold exists.

BUSINESS_RULES.md: "A free or strict-higher-urgency-preemptible candidate may be asked of the
handyman" and a selected request "transfers all overlapping lower-urgency tentative holds
atomically, only if no equal/higher hold or confirmed visit overlaps". Offering a still-free slot
to both orders is therefore allowed; arbitration happens at hold time and the commit never
produces two overlapping appointments.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from maintenance_agent.application.conversation import AvailabilityInterpretation
from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.application.scheduling import CandidateAvailability
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.negotiation import PendingAction, TimeInterval
from maintenance_agent.domain.scheduling import overlaps
from maintenance_agent.domain.work_orders import Urgency, WorkOrder
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority
from tests.integration.fakes import FakeConversationHandler

MADRID = ZoneInfo("Europe/Madrid")
NOW = datetime(2026, 10, 12, 12, tzinfo=MADRID)


def _interval(start_hour: int, end_hour: int) -> TimeInterval:
    return TimeInterval(
        datetime(2026, 10, 13, start_hour, tzinfo=MADRID),
        datetime(2026, 10, 13, end_hour, tzinfo=MADRID),
    )


def _order(order_id: str, urgency: Urgency) -> WorkOrder:
    return WorkOrder(
        work_order_id=order_id,
        work_order="Leak",
        address="Calle Sol 4",
        description="Issue",
        reported_at=datetime(2026, 10, 12, tzinfo=MADRID),
        urgency=urgency,
    )


def _result() -> list[AvailabilityInterpretation]:
    return [AvailabilityInterpretation((_interval(9, 11),), True, False)]


class _Order:
    def __init__(self, agenda: InMemoryScheduleAuthority, order_id: str, urgency: Urgency) -> None:
        self.id = order_id
        handler = FakeConversationHandler(
            availability_results={"tenant": _result(), "handyman": _result()}
        )
        self.workflow = NegotiationWorkflow(handler, agenda, clock=lambda: NOW)
        self.order = _order(order_id, urgency)
        self.state: dict = {}

    async def begin(self) -> None:
        self.state = await self.workflow.start(
            self.order, LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
        )

    async def say(self, role: str, text: str = "yes") -> dict:
        self.state = await self.workflow.handle(self.state, InboundMessage(self.id, role, text))
        return self.state


async def _both_proposed():
    agenda = InMemoryScheduleAuthority()
    critical = _Order(agenda, "WO-001", Urgency.CRITICAL)
    low = _Order(agenda, "WO-003", Urgency.LOW)
    for item in (critical, low):
        await item.begin()
        await item.say("tenant", "9 to 11")
    # No hold exists yet: both are asked about the very same free slot.
    for item in (critical, low):
        assert item.state["pending_question"].action is PendingAction.HANDYMAN_AVAILABILITY
        inspected = await agenda.inspect_candidates(item.state["candidates"], item.order.urgency)
        assert inspected[0].availability is CandidateAvailability.FREE
    for item in (critical, low):
        await item.say("handyman", "9 to 11")
        await item.say("handyman", "yes")  # handyman availability is read back first
        assert item.state["proposal"].candidate.interval == _interval(9, 11)
    return agenda, critical, low


async def _assert_no_overlap(agenda: InMemoryScheduleAuthority) -> tuple[str, ...]:
    appointments = (await agenda.snapshot()).appointments
    for index, first in enumerate(appointments):
        for second in appointments[index + 1 :]:
            assert not overlaps(first.interval, second.interval)
    return tuple(item.work_order_id for item in appointments)


@pytest.mark.asyncio
async def test_critical_displaces_low_hold_and_only_critical_is_scheduled() -> None:
    agenda, critical, low = await _both_proposed()
    await low.say("tenant")  # low gets the tentative hold first
    assert [h.work_order_id for h in (await agenda.snapshot()).holds] == ["WO-003"]
    await critical.say("tenant")  # strictly higher urgency transfers the hold
    assert [h.work_order_id for h in (await agenda.snapshot()).holds] == ["WO-001"]
    await low.say("handyman")  # the displaced order can no longer commit
    assert low.state.get("terminal_status") is None
    await critical.say("handyman")
    assert await _assert_no_overlap(agenda) == ("WO-001",)


@pytest.mark.asyncio
async def test_low_cannot_take_the_slot_while_critical_holds_it() -> None:
    agenda, critical, low = await _both_proposed()
    await critical.say("tenant")
    await low.say("tenant")
    assert low.state["pending_question"].action is PendingAction.TENANT_ALTERNATIVES
    await critical.say("handyman")
    assert await _assert_no_overlap(agenda) == ("WO-001",)


@pytest.mark.asyncio
async def test_confirmed_appointment_is_never_preempted_by_a_later_critical() -> None:
    agenda, critical, low = await _both_proposed()
    await low.say("tenant")
    await low.say("handyman")  # low is confirmed before critical selects the slot
    assert await _assert_no_overlap(agenda) == ("WO-003",)
    await critical.say("tenant")
    assert critical.state["pending_question"].action is PendingAction.TENANT_ALTERNATIVES
    assert await _assert_no_overlap(agenda) == ("WO-003",)
