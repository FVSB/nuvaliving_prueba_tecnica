from datetime import datetime, timedelta, timezone

import pytest

from maintenance_agent.application.conversation import AvailabilityInterpretation
from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.negotiation import (
    ParticipantRole,
    PendingAction,
    TerminalStatus,
    TimeInterval,
)
from maintenance_agent.domain.work_orders import Urgency, WorkOrder
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority
from tests.integration.fakes import FakeConversationHandler

_NOW = datetime.fromisoformat("2026-10-12T12:00:00+02:00")


ORDER_ID = "WO-ROLE"


def _interval(start_hour: int, end_hour: int, day: int = 13) -> TimeInterval:
    base = datetime(2026, 10, day, tzinfo=timezone(timedelta(hours=2)))
    return TimeInterval(
        base.replace(hour=start_hour).astimezone(timezone.utc),
        base.replace(hour=end_hour).astimezone(timezone.utc),
    )


def _order() -> WorkOrder:
    return WorkOrder(
        work_order_id=ORDER_ID,
        work_order="Leak",
        address="Calle Sol 4",
        description="Water leak",
        reported_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
        urgency=Urgency.HIGH,
    )


async def _awaiting_handyman(handler: FakeConversationHandler):
    agenda = InMemoryScheduleAuthority()
    workflow = NegotiationWorkflow(handler, agenda, clock=lambda: _NOW)
    state = await workflow.start(
        _order(), LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
    )
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "13th 9 to 13"))
    assert state["pending_question"].action is PendingAction.HANDYMAN_AVAILABILITY
    return workflow, agenda, state


@pytest.mark.asyncio
async def test_tenant_message_never_becomes_handyman_evidence() -> None:
    handler = FakeConversationHandler(
        availability_results={
            "tenant": [AvailabilityInterpretation((_interval(9, 13),), True, False)],
        }
    )
    workflow, agenda, state = await _awaiting_handyman(handler)
    question_id = state["pending_question"].question_id

    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "Who is coming?"))
    assert state["outbound_message"].role == "tenant"
    assert state["pending_question"].question_id == question_id
    assert state["pending_question"].role is ParticipantRole.HANDYMAN

    state = await workflow.handle(
        state, InboundMessage(ORDER_ID, "tenant", "I am free on 2026-10-13 from 10 to 12")
    )
    assert state["outbound_message"].role == "tenant"
    assert state["pending_question"].question_id == question_id
    assert state.get("handyman_evidence") is None
    evidence = (await agenda.snapshot()).evidence
    assert all(item.role is ParticipantRole.TENANT for item in evidence)
    assert [call[1] for call in handler.availability_calls] == [ParticipantRole.TENANT]


@pytest.mark.asyncio
async def test_handyman_still_answers_after_tenant_reminder() -> None:
    handler = FakeConversationHandler(
        availability_results={
            "tenant": [AvailabilityInterpretation((_interval(9, 13),), True, False)],
            "handyman": [AvailabilityInterpretation((_interval(9, 13),), True, False)],
        }
    )
    workflow, _, state = await _awaiting_handyman(handler)
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "hello?"))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "disponible"))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "yes"))
    assert state["handyman_evidence"].role is ParticipantRole.HANDYMAN
    assert state["pending_question"].action is PendingAction.TENANT_CONFIRMATION


@pytest.mark.asyncio
async def test_no_response_is_attributed_to_the_role_with_the_pending_question() -> None:
    handler = FakeConversationHandler(
        availability_results={
            "tenant": [AvailabilityInterpretation((_interval(9, 13),), True, False)],
        }
    )
    workflow, _, state = await _awaiting_handyman(handler)
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "<NO RESPONSE>"))
    assert state["terminal_status"] is TerminalStatus.REQUIRES_REVIEW
    line = state["terminal_frame"].detail
    assert line.startswith("REASON:No response from handyman while awaiting")
    assert "silent role handyman" in line
    assert "\n" not in line


@pytest.mark.asyncio
async def test_no_response_sentinel_from_other_role_blames_pending_role() -> None:
    handler = FakeConversationHandler(
        availability_results={
            "tenant": [AvailabilityInterpretation((_interval(9, 13),), True, False)],
        }
    )
    workflow, _, state = await _awaiting_handyman(handler)
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "<NO RESPONSE>"))
    assert state["terminal_frame"].detail.startswith("REASON:No response from handyman")
