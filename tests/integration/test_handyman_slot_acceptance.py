from datetime import datetime, timedelta, timezone

import pytest

from maintenance_agent.application.conversation import AvailabilityInterpretation
from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.negotiation import PendingAction, TimeInterval
from maintenance_agent.domain.work_orders import Urgency, WorkOrder
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority
from tests.integration.fakes import FakeConversationHandler

_NOW = datetime.fromisoformat("2026-10-12T12:00:00+02:00")


ORDER_ID = "WO-ACCEPT"


def _interval(start_hour: int, end_hour: int, day: int = 13) -> TimeInterval:
    base = datetime(2026, 10, day, tzinfo=timezone(timedelta(hours=2)))
    return TimeInterval(
        base.replace(hour=start_hour).astimezone(timezone.utc),
        base.replace(hour=end_hour).astimezone(timezone.utc),
    )


async def _awaiting_handyman(handler: FakeConversationHandler, *tenant_intervals: TimeInterval):
    workflow = NegotiationWorkflow(handler, InMemoryScheduleAuthority(), clock=lambda: _NOW)
    order = WorkOrder(
        work_order_id=ORDER_ID,
        work_order="Leak",
        address="Calle Sol 4",
        description="Water leak",
        reported_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
        urgency=Urgency.HIGH,
    )
    state = await workflow.start(
        order, LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
    )
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "window"))
    assert state["pending_question"].action is PendingAction.HANDYMAN_AVAILABILITY
    return workflow, state


def _tenant_handler(*intervals: TimeInterval) -> FakeConversationHandler:
    return FakeConversationHandler(
        availability_results={"tenant": [AvailabilityInterpretation(tuple(intervals), True, False)]}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "Sí, me viene bien el 13 de octubre de 2026 de 9:00 a 11:00",
        "Sí, me viene bien el de 9:00 a 11:00",
        "yes, 2026-10-13 from 9:00 to 11:00",
    ],
)
async def test_affirmation_naming_a_proposed_slot_is_accepted(text: str) -> None:
    handler = _tenant_handler(_interval(9, 13))
    workflow, state = await _awaiting_handyman(handler)
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", text))
    assert state["handyman_evidence"].intervals == (_interval(9, 11),)
    assert state["proposal"].candidate.interval == _interval(9, 11)
    assert state["pending_question"].action is PendingAction.TENANT_CONFIRMATION
    assert [call[1].value for call in handler.availability_calls] == ["tenant"]


@pytest.mark.asyncio
async def test_affirmation_with_a_different_range_is_new_availability() -> None:
    handler = _tenant_handler(_interval(9, 13))
    handler.availability_results["handyman"] = [
        AvailabilityInterpretation((_interval(10, 12),), True, False)
    ]
    workflow, state = await _awaiting_handyman(handler)
    text = "Sí, me viene bien el 13 de octubre de 10:00 a 12:00"
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", text))
    assert state["pending_question"].action is PendingAction.RELATIVE_DATE_CONFIRMATION
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "yes"))
    assert [call[1].value for call in handler.availability_calls] == ["tenant", "handyman"]
    assert state["handyman_evidence"].intervals == (_interval(10, 12),)


@pytest.mark.asyncio
async def test_affirmation_matching_several_days_asks_which_one() -> None:
    handler = _tenant_handler(_interval(9, 11), _interval(9, 11, day=14))
    workflow, state = await _awaiting_handyman(handler)
    state = await workflow.handle(
        state, InboundMessage(ORDER_ID, "handyman", "Sí, me viene bien de 9:00 a 11:00")
    )
    assert state.get("handyman_evidence") is None
    assert state["pending_question"].action is PendingAction.HANDYMAN_AVAILABILITY
    assert state["outbound_message"].role == "handyman"


@pytest.mark.asyncio
async def test_handyman_intervals_need_explicit_confirmation_before_counting() -> None:
    handler = _tenant_handler(_interval(9, 13))
    handler.availability_results["handyman"] = [
        AvailabilityInterpretation((_interval(10, 12),), True, False)
    ]
    workflow, state = await _awaiting_handyman(handler)
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "tengo de 10 a 12"))
    assert state.get("handyman_evidence") is None
    assert state["pending_question"].action is PendingAction.RELATIVE_DATE_CONFIRMATION
    assert state["pending_question"].role.value == "handyman"
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "no"))
    assert state.get("handyman_evidence") is None
    assert state["pending_question"].action is PendingAction.HANDYMAN_AVAILABILITY


@pytest.mark.asyncio
async def test_bare_yes_accepts_the_single_slot_offered() -> None:
    workflow, state = await _awaiting_handyman(_tenant_handler(_interval(9, 11)))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "si puedo"))
    assert state["handyman_evidence"].intervals == (_interval(9, 11),)
    assert state["pending_question"].action is PendingAction.TENANT_CONFIRMATION


@pytest.mark.asyncio
async def test_bare_yes_with_several_slots_asks_which() -> None:
    workflow, state = await _awaiting_handyman(_tenant_handler(_interval(9, 13)))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "si puedo"))
    assert state.get("handyman_evidence") is None
    assert state["pending_question"].action is PendingAction.HANDYMAN_AVAILABILITY


@pytest.mark.asyncio
async def test_single_offer_is_a_yes_no_question_and_no_asks_for_intervals() -> None:
    handler = _tenant_handler(_interval(9, 11))
    workflow, state = await _awaiting_handyman(handler)
    assert any("'sí' or 'no'" in intent for intent, _, _ in handler.compositions)
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "no puedo"))
    assert state.get("handyman_evidence") is None
    assert state["pending_question"].action is PendingAction.HANDYMAN_AVAILABILITY
    assert handler.availability_calls[-1][1].value == "tenant"


@pytest.mark.asyncio
async def test_declined_slot_is_not_reoffered_or_accepted_by_a_later_yes() -> None:
    workflow, state = await _awaiting_handyman(_tenant_handler(_interval(9, 11)))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "no"))
    assert state["candidates"] == ()
    assert state["handyman_declined"] == (_interval(9, 11),)
    assert any(e["event_type"] == "handyman_slots_declined" for e in state["trace_events"])
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "sí"))
    assert state.get("handyman_evidence") is None
    assert state.get("proposal") is None
    assert state["pending_question"].action is PendingAction.HANDYMAN_AVAILABILITY


@pytest.mark.asyncio
async def test_tenant_message_while_handyman_pending_says_we_are_waiting() -> None:
    workflow, state = await _awaiting_handyman(_tenant_handler(_interval(9, 11)))
    question = state["pending_question"]
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "yes"))
    assert state["pending_question"] == question
    assert state["outbound_message"].role == "tenant"
    assert "other party answers" in state["outbound_message"].body


@pytest.mark.asyncio
async def test_natural_acceptance_binds_the_single_slot_offered() -> None:
    workflow, state = await _awaiting_handyman(_tenant_handler(_interval(9, 11)))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "ok me gusta"))
    assert state["handyman_evidence"].intervals == (_interval(9, 11),)
    assert state["pending_question"].action is PendingAction.TENANT_CONFIRMATION


@pytest.mark.asyncio
async def test_natural_acceptance_with_several_slots_asks_which() -> None:
    workflow, state = await _awaiting_handyman(_tenant_handler(_interval(9, 13)))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "ok me gusta"))
    assert state.get("handyman_evidence") is None
    assert state["pending_question"].action is PendingAction.HANDYMAN_AVAILABILITY


@pytest.mark.asyncio
async def test_natural_acceptance_confirms_the_single_proposal_for_the_tenant() -> None:
    workflow, state = await _awaiting_handyman(_tenant_handler(_interval(9, 11)))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "si puedo"))
    assert state["pending_question"].action is PendingAction.TENANT_CONFIRMATION
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "ok me gusta"))
    assert state["pending_question"].action is PendingAction.HANDYMAN_CONFIRMATION
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "ok me gusta"))
    assert state["terminal_status"].value == "scheduled"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tenant_text",
    [
        "Yes, I accept 2026-10-13 9:00-11:00.",
        "Sí, acepto el 13 de octubre de 9:00 a 11:00",
    ],
)
async def test_acceptance_restating_the_proposed_date_and_time_counts(tenant_text: str) -> None:
    workflow, state = await _awaiting_handyman(_tenant_handler(_interval(9, 11)))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "si puedo"))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", tenant_text))
    assert state["pending_question"].action is PendingAction.HANDYMAN_CONFIRMATION


@pytest.mark.asyncio
async def test_acceptance_naming_a_different_time_does_not_count() -> None:
    workflow, state = await _awaiting_handyman(_tenant_handler(_interval(9, 11)))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "si puedo"))
    state = await workflow.handle(
        state, InboundMessage(ORDER_ID, "tenant", "Yes, I accept 2026-10-13 15:00-17:00.")
    )
    assert state["pending_question"].action is PendingAction.TENANT_CONFIRMATION
    assert state.get("terminal_status") is None
