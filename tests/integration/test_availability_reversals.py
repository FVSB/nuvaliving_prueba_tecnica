from datetime import datetime, timedelta, timezone

import pytest

from maintenance_agent.application.conversation import AvailabilityInterpretation
from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.negotiation import ParticipantRole, TimeInterval
from maintenance_agent.domain.work_orders import Urgency, WorkOrder
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority
from tests.integration.fakes import FakeConversationHandler


def _window(start_hour: int) -> TimeInterval:
    start = datetime(2026, 10, 20, start_hour, tzinfo=timezone.utc)
    return TimeInterval(start, start + timedelta(hours=4))


@pytest.mark.asyncio
async def test_tenant_reversal_suspends_old_evidence_until_sender_confirms_new() -> None:
    old_window, new_window, handyman_window = _window(7), _window(8), _window(7)
    handler = FakeConversationHandler(
        availability_results={
            "tenant": [
                AvailabilityInterpretation((old_window,), True, False),
                AvailabilityInterpretation((new_window,), True, False),
            ],
            "handyman": [AvailabilityInterpretation((handyman_window,), True, False)],
        }
    )
    agenda = InMemoryScheduleAuthority()
    workflow = NegotiationWorkflow(handler, agenda)
    order = WorkOrder(
        work_order_id="WO-REV",
        work_order="Leak",
        address="Calle Sol 4",
        description="Water leak",
        reported_at=old_window.start,
        urgency=Urgency.HIGH,
    )
    state = await workflow.start(
        order, LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
    )
    state = await workflow.handle(state, InboundMessage("WO-REV", "tenant", "first interval"))
    state = await workflow.handle(state, InboundMessage("WO-REV", "handyman", "available"))
    state = await workflow.handle(state, InboundMessage("WO-REV", "tenant", "no"))
    state = await workflow.handle(state, InboundMessage("WO-REV", "tenant", "no"))
    state = await workflow.handle(state, InboundMessage("WO-REV", "tenant", "changed interval"))
    assert state["pending_question"].action.value == "availability_change"
    assert state["proposal"] is None
    assert state["tenant_evidence"].disputed is True
    assert state["tenant_evidence"].intervals == (old_window,)
    evidence = (await agenda.snapshot()).evidence
    assert any(item.role is ParticipantRole.TENANT and item.disputed for item in evidence)

    state = await workflow.handle(state, InboundMessage("WO-REV", "tenant", "yes"))
    assert state["tenant_evidence"].intervals == (new_window,)
    assert state["tenant_evidence"].disputed is False
    assert state["pending_question"].role is ParticipantRole.HANDYMAN
