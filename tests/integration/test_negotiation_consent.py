from datetime import datetime, timedelta, timezone

import pytest

from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.negotiation import ParticipantRole, TerminalStatus
from maintenance_agent.domain.work_orders import Urgency, WorkOrder
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority
from tests.integration.fakes import FakeConversationHandler

_NOW = datetime.fromisoformat("2026-10-16T12:00:00+02:00")


@pytest.mark.asyncio
async def test_matching_role_consents_commit_then_finalize_both_participants() -> None:
    start = datetime(2026, 10, 20, 7, tzinfo=timezone.utc)
    end = start + timedelta(hours=4)
    handler = FakeConversationHandler(
        availability={
            "tenant": ((start.isoformat(), end.isoformat()),),
            "handyman": ((start.isoformat(), end.isoformat()),),
        },
    )
    agenda = InMemoryScheduleAuthority()
    workflow = NegotiationWorkflow(handler, agenda, clock=lambda: _NOW)
    order = WorkOrder(
        work_order_id="WO-CONSENT",
        work_order="Leak",
        address="Calle Sol 4",
        description="Water leak under the sink",
        reported_at=start,
        urgency=Urgency.HIGH,
    )
    state = await workflow.start(
        order, LanguageRecognitionResult(language_code=LanguageCode.SPANISH)
    )
    state = await workflow.handle(state, InboundMessage(order.work_order_id, "tenant", "available"))
    state = await workflow.handle(
        state, InboundMessage(order.work_order_id, "handyman", "available")
    )
    state = await workflow.handle(state, InboundMessage(order.work_order_id, "handyman", "yes"))
    state = await workflow.handle(state, InboundMessage(order.work_order_id, "tenant", "yes"))
    assert state["pending_question"].role is ParticipantRole.HANDYMAN
    assert state.get("terminal_status") is None
    state = await workflow.handle(state, InboundMessage(order.work_order_id, "handyman", "yes"))
    assert state["terminal_status"] is TerminalStatus.SCHEDULED
    assert state["finalization_pending"] is True
    assert len((await agenda.snapshot()).appointments) == 1
    assert state["outbound_message"].role == "tenant"
    state = await workflow.continue_finalization(state)
    assert state["outbound_message"].role == "handyman"
    state = await workflow.continue_finalization(state)
    assert state["terminal_frame"].result == "scheduled"
    assert state["terminal_frame"].detail.startswith("SCHEDULED_FOR:2026-10-20T09:00:00+02:00")
