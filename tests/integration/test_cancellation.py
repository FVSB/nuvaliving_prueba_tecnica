from datetime import datetime, timedelta, timezone

import pytest

from maintenance_agent.application.conversation import AvailabilityInterpretation
from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.negotiation import ParticipantRole, PendingAction, TimeInterval
from maintenance_agent.domain.work_orders import Urgency, WorkOrder
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority
from tests.integration.fakes import FakeConversationHandler

_NOW = datetime.fromisoformat("2026-10-12T12:00:00+02:00")


ORDER_ID = "WO-CANCEL"


def _interval(start_hour: int, end_hour: int, day: int = 13) -> TimeInterval:
    base = datetime(2026, 10, day, tzinfo=timezone(timedelta(hours=2)))
    return TimeInterval(
        base.replace(hour=start_hour).astimezone(timezone.utc),
        base.replace(hour=end_hour).astimezone(timezone.utc),
    )


def _result(*intervals: TimeInterval) -> AvailabilityInterpretation:
    return AvailabilityInterpretation(tuple(intervals), True, False)


def _order() -> WorkOrder:
    return WorkOrder(
        work_order_id=ORDER_ID,
        work_order="Leak",
        address="Calle Sol 4",
        description="Water leak",
        reported_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
        urgency=Urgency.HIGH,
    )


async def _proposal_pending(handler: FakeConversationHandler):
    agenda = InMemoryScheduleAuthority()
    workflow = NegotiationWorkflow(handler, agenda, clock=lambda: _NOW)
    state = await workflow.start(
        _order(), LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
    )
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "tenant window"))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "handyman window"))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "yes"))
    assert state["pending_question"].action is PendingAction.TENANT_CONFIRMATION
    return workflow, agenda, state


def _handler(*extra_tenant: AvailabilityInterpretation) -> FakeConversationHandler:
    return FakeConversationHandler(
        availability_results={
            "tenant": [_result(_interval(9, 13)), *extra_tenant],
            "handyman": [_result(_interval(9, 13))],
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["No, cancelo, ya no me sirve", "cancelar", "cancel"])
async def test_tenant_cancel_rejects_proposal_and_requests_alternatives(text: str) -> None:
    workflow, agenda, state = await _proposal_pending(_handler())
    assert (await agenda.snapshot()).holds == ()
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", text))
    assert state["pending_question"].action is PendingAction.TENANT_ALTERNATIVES
    assert state["outbound_message"].role == "tenant"
    assert (await agenda.snapshot()).holds == ()
    assert state.get("terminal_status") is None


@pytest.mark.asyncio
async def test_cancel_after_tenant_yes_releases_hold() -> None:
    workflow, agenda, state = await _proposal_pending(_handler())
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "yes"))
    assert state["pending_question"].action is PendingAction.HANDYMAN_CONFIRMATION
    assert len((await agenda.snapshot()).holds) == 1
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "cancelar"))
    assert (await agenda.snapshot()).holds == ()
    assert state["pending_question"].action is PendingAction.TENANT_ALTERNATIVES
    assert state["pending_question"].role is ParticipantRole.TENANT
    assert (await agenda.snapshot()).appointments == ()


@pytest.mark.asyncio
async def test_availability_correction_requires_sender_confirmation() -> None:
    corrected = _result(_interval(10, 12, day=14))
    workflow, agenda, state = await _proposal_pending(_handler(corrected))
    old_proposal = state["proposal"]
    state = await workflow.handle(
        state, InboundMessage(ORDER_ID, "tenant", "Perdón, mejor el 2026-10-14 de 10:00 a 12:00")
    )
    assert state["pending_question"].action is PendingAction.AVAILABILITY_CHANGE
    assert state["pending_question"].role is ParticipantRole.TENANT
    assert state["proposal"] is None
    assert state["tenant_evidence"].disputed is True
    assert state["disputed_availability"]["proposed"].intervals == (_interval(10, 12, day=14),)
    holds = (await agenda.snapshot()).holds
    assert all(hold.proposal_id != old_proposal.proposal_id for hold in holds)

    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "yes"))
    assert state["tenant_evidence"].intervals == (_interval(10, 12, day=14),)
    assert state["tenant_evidence"].disputed is False


@pytest.mark.asyncio
async def test_unclear_reply_without_new_intervals_still_asks_for_yes_or_no() -> None:
    workflow, _, state = await _proposal_pending(_handler(_result()))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "hmm maybe"))
    assert state["pending_question"].action is PendingAction.TENANT_CONFIRMATION
    assert state["proposal"] is not None
