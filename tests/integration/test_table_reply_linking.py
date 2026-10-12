"""A day/time reply after the slot table is bound to the slots that were shown."""

import pytest

from maintenance_agent.application.conversation import (
    AvailabilityInterpretation,
    MessageClass,
    PartOfDay,
)
from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.negotiation import PendingAction
from tests.integration.fakes import FakeConversationHandler
from tests.unit.slot_helpers import MADRID, NOW, VAGUE, StubAgenda, appointment_at, started

FRIDAY = "2026-10-16"


def _vague(date_from=None, date_to=None, part=PartOfDay.NONE) -> AvailabilityInterpretation:
    return AvailabilityInterpretation(
        (),
        False,
        True,
        classification=MessageClass.VAGUE_DATE_REQUEST,
        date_from=date_from,
        date_to=date_to,
        part_of_day=part,
    )


async def _after_table(first: AvailabilityInterpretation, second, *appointments):
    handler = FakeConversationHandler(availability_results={"tenant": [first, second]})
    workflow = NegotiationWorkflow(
        handler, StubAgenda(*appointments), "Europe/Madrid", clock=lambda: NOW
    )
    state = await workflow.handle(
        await started(workflow), InboundMessage("WO-S1", "tenant", "esta semana")
    )
    assert state["slot_table_request"] is not None
    state = await workflow.handle(state, InboundMessage("WO-S1", "tenant", "el viernes"))
    return handler, state


@pytest.mark.asyncio
async def test_single_matching_slot_is_taken_as_the_chosen_interval() -> None:
    _, state = await _after_table(VAGUE, _vague(FRIDAY, FRIDAY, PartOfDay.MORNING))
    chosen = state["tenant_evidence"].intervals
    assert len(chosen) == 1
    assert chosen[0].start.astimezone(MADRID).isoformat() == "2026-10-16T09:00:00+02:00"
    assert chosen[0].end.astimezone(MADRID).hour == 11
    assert state["pending_question"].action is PendingAction.HANDYMAN_AVAILABILITY
    assert state["slot_table_request"] is None
    events = [e for e in state["trace_events"] if e["event_type"] == "table_reply_linked"]
    assert events and len(events[0]["detail"]["matches"]) == 1


@pytest.mark.asyncio
async def test_several_matching_slots_show_only_those_and_ask_which() -> None:
    _, state = await _after_table(VAGUE, _vague(FRIDAY, FRIDAY))
    body = state["outbound_message"].body
    assert "09:00–11:00" in body and "17:00–19:00" in body
    assert "2026-10-16" in body and "2026-10-15" not in body and "2026-10-14" not in body
    assert "SLOT-" not in body
    assert state.get("tenant_evidence") is None
    assert state["pending_question"].action is PendingAction.TENANT_AVAILABILITY
    assert "Spanish: ask" in body


@pytest.mark.asyncio
async def test_follow_up_after_narrowed_table_picks_from_the_narrowed_slots() -> None:
    handler = FakeConversationHandler(
        availability_results={
            "tenant": [VAGUE, _vague(FRIDAY, FRIDAY), _vague(FRIDAY, FRIDAY, PartOfDay.MORNING)]
        }
    )
    workflow = NegotiationWorkflow(handler, StubAgenda(), "Europe/Madrid", clock=lambda: NOW)
    state = await started(workflow)
    for text in ("esta semana", "el viernes", "viernes por la manana"):
        state = await workflow.handle(state, InboundMessage("WO-S1", "tenant", text))
    chosen = state["tenant_evidence"].intervals[0]
    assert chosen.start.astimezone(MADRID).hour == 9


@pytest.mark.asyncio
async def test_no_matching_slot_says_so_with_the_reason_not_a_generic_reask() -> None:
    booked = [appointment_at(hour, day=16) for hour in (9, 11, 13, 15, 17)]
    _, state = await _after_table(
        _vague("2026-10-13", "2026-10-13"), _vague(FRIDAY, FRIDAY), *booked
    )
    body = state["outbound_message"].body
    assert "No hay espacios libres para el día y la franja solicitados." in body
    assert state.get("tenant_evidence") is None
    assert state["pending_question"].action is PendingAction.TENANT_AVAILABILITY


async def _reply_without_model_dates(text: str, *appointments):
    handler = FakeConversationHandler(availability_results={"tenant": [VAGUE, _vague()]})
    workflow = NegotiationWorkflow(
        handler, StubAgenda(*appointments), "Europe/Madrid", clock=lambda: NOW
    )
    state = await workflow.handle(
        await started(workflow), InboundMessage("WO-S1", "tenant", "esta semana")
    )
    return await workflow.handle(state, InboundMessage("WO-S1", "tenant", text))


@pytest.mark.asyncio
async def test_weekday_without_model_dates_lists_only_that_day() -> None:
    state = await _reply_without_model_dates("el viernes")
    body = state["outbound_message"].body
    assert "2026-10-16" in body and "2026-10-15" not in body and "SLOT-" not in body
    assert state.get("tenant_evidence") is None


@pytest.mark.asyncio
async def test_weekday_and_hour_without_model_dates_pick_the_covering_slot() -> None:
    state = await _reply_without_model_dates("viernes a las 10")
    chosen = state["tenant_evidence"].intervals[0]
    assert chosen.start.astimezone(MADRID).isoformat() == "2026-10-16T09:00:00+02:00"


@pytest.mark.asyncio
async def test_day_of_month_without_model_dates_matches_the_shown_day() -> None:
    state = await _reply_without_model_dates("el 14 a las 3")
    chosen = state["tenant_evidence"].intervals[0]
    assert chosen.start.astimezone(MADRID).isoformat() == "2026-10-14T15:00:00+02:00"


@pytest.mark.asyncio
async def test_day_beyond_the_horizon_states_the_availability_limit() -> None:
    state = await _reply_without_model_dates("el 23")
    assert "Solo conozco la disponibilidad hasta el lunes 2026-10-19" in (
        state["outbound_message"].body
    )
    assert state.get("tenant_evidence") is None
    assert state["pending_question"].action is PendingAction.TENANT_AVAILABILITY
