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


def order(order_id="WO-LANG"):
    return WorkOrder(
        work_order_id=order_id,
        work_order="Leak repair",
        address="Calle Sol 4",
        description="Water is leaking beneath the kitchen sink.",
        reported_at=datetime(2026, 10, 12, 9, tzinfo=timezone.utc),
        urgency=Urgency.HIGH,
    )


@pytest.mark.asyncio
async def test_tenant_availability_is_first_and_creates_full_utc_candidates() -> None:
    start = datetime(2026, 10, 20, 7, tzinfo=timezone.utc)
    handler = FakeConversationHandler(
        availability={
            "tenant": ((start.isoformat(), (start + timedelta(hours=4)).isoformat()),),
        }
    )
    workflow = NegotiationWorkflow(handler, InMemoryScheduleAuthority())
    state = await workflow.start(
        order(), LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
    )
    assert state["pending_question"].role is ParticipantRole.TENANT
    assert state["outbound_message"].role == "tenant"
    state = await workflow.handle(state, InboundMessage("WO-LANG", "tenant", "Oct 20, 9 to 13"))
    assert state["outbound_message"].role == "handyman"
    assert [item.interval.start for item in state["candidates"]] == [
        start,
        start + timedelta(hours=2),
    ]
    assert state["tenant_evidence"].intervals[0].start == start
    assert handler.compositions[0][1] == "English"


@pytest.mark.asyncio
async def test_one_complete_interval_with_no_more_dates_is_accepted() -> None:
    start = datetime(2027, 1, 15, 13, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    handler = FakeConversationHandler(
        availability={"tenant": ((start.isoformat(), end.isoformat()),)}
    )
    workflow = NegotiationWorkflow(handler, InMemoryScheduleAuthority())
    state = await workflow.start(
        order(), LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
    )

    state = await workflow.handle(
        state,
        InboundMessage(
            "WO-LANG",
            "tenant",
            "I'm available January 15th from 2 PM to 4 PM; no tengo más fechas",
        ),
    )

    assert state["pending_question"].role is ParticipantRole.HANDYMAN
    assert state["tenant_evidence"].intervals == (state["candidates"][0].interval,)
    assert len(state["candidates"]) == 1


@pytest.mark.asyncio
async def test_llm_relative_weekday_suggestion_is_confirmed_before_recording() -> None:
    reference = datetime(2026, 10, 12, 10, tzinfo=__import__("zoneinfo").ZoneInfo("Europe/Madrid"))
    proposed = TimeInterval(
        datetime(2026, 10, 19, 12, tzinfo=reference.tzinfo),
        datetime(2026, 10, 19, 14, tzinfo=reference.tzinfo),
    )
    handler = FakeConversationHandler(
        availability_results={
            "tenant": (
                AvailabilityInterpretation(
                    intervals=(),
                    complete=False,
                    clarification_required=False,
                    suggested_intervals=(proposed,),
                    date_confirmation_required=True,
                ),
            )
        },
    )
    workflow = NegotiationWorkflow(handler, InMemoryScheduleAuthority(), clock=lambda: reference)
    state = await workflow.start(
        order(), LanguageRecognitionResult(language_code=LanguageCode.SPANISH)
    )

    state = await workflow.handle(state, InboundMessage("WO-LANG", "tenant", "lunes de 12-14"))

    assert state["pending_question"].action is PendingAction.RELATIVE_DATE_CONFIRMATION
    assert state["tenant_evidence"] is None
    assert state["candidates"] == ()
    assert "2026-10-19" in str(handler.compositions[-1][2])
    assert handler.availability_calls[-1][2] == reference
    assert handler.availability_calls[-1][3] == "Europe/Madrid"

    state = await workflow.handle(state, InboundMessage("WO-LANG", "tenant", "sí"))

    assert state["tenant_evidence"].intervals == (proposed,)
    assert state["outbound_message"].role == "handyman"


@pytest.mark.asyncio
async def test_twelve_am_without_end_time_stays_in_clarification() -> None:
    reference = datetime(2026, 10, 12, 10, tzinfo=__import__("zoneinfo").ZoneInfo("Europe/Madrid"))
    handler = FakeConversationHandler(
        availability_results={
            "tenant": (
                AvailabilityInterpretation(
                    intervals=(),
                    complete=False,
                    clarification_required=True,
                    clarification="12am means midnight; please provide the end time.",
                ),
            )
        }
    )
    workflow = NegotiationWorkflow(handler, InMemoryScheduleAuthority(), clock=lambda: reference)
    state = await workflow.start(
        order(), LanguageRecognitionResult(language_code=LanguageCode.SPANISH)
    )

    state = await workflow.handle(state, InboundMessage("WO-LANG", "tenant", "lunes a las 12am"))

    assert state["tenant_evidence"] is None
    assert state["candidates"] == ()
    assert state["pending_question"].action is PendingAction.TENANT_AVAILABILITY
    assert "12am means midnight" in str(handler.compositions[-1][2])
