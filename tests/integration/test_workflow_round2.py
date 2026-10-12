"""Round 2 workflow fixes: fallback table, linking, horizon, compose facts, alternatives, traces."""

from datetime import date, datetime

import pytest

from maintenance_agent.application.conversation import (
    AvailabilityInterpretation,
    MessageClass,
    PartOfDay,
)
from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.application.slot_table import (
    OpenSlot,
    format_local_date,
    match_table_reference,
    parse_table_reference,
)
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.negotiation import PendingAction, TimeInterval
from tests.integration.fakes import BAD_PROSE, FakeConversationHandler
from tests.integration.test_cancellation import (
    ORDER_ID,
    _handler,
    _interval,
    _proposal_pending,
    _result,
)
from tests.unit.slot_helpers import MADRID, StubAgenda, started

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=MADRID)
VAGUE = AvailabilityInterpretation((), False, True, classification=MessageClass.VAGUE_DATE_REQUEST)


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


def _msg(text: str) -> InboundMessage:
    return InboundMessage("WO-S1", "tenant", text)


def _workflow(handler: FakeConversationHandler) -> NegotiationWorkflow:
    return NegotiationWorkflow(handler, StubAgenda(), "Europe/Madrid", clock=lambda: NOW)


def _failing_prose() -> list[tuple[str, str]]:
    return [BAD_PROSE] * 6


# 1(b) fallback with table ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_after_exhausted_attempts_includes_table_and_keeps_it_linkable() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [_vague("2026-10-16", "2026-10-16"), _vague()]},
        slot_prose=_failing_prose(),
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("el viernes"))
    body = state["outbound_message"].body
    assert "| 2026-10-16" in body and "2026-10-15" not in body and "SLOT-" not in body
    assert "tabla" in body
    assert state["trace_events"][-1]["event_type"] == "slot_fallback_emitted"
    assert state["slot_table_request"] is not None


@pytest.mark.asyncio
async def test_fallback_for_window_partly_beyond_horizon_adds_the_limit_phrase() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [_vague("2026-10-19", "2026-10-25")]},
        slot_prose=_failing_prose(),
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("la semana que viene"))
    body = state["outbound_message"].body
    assert "| 2026-10-19" in body and "2026-10-20" not in body
    assert "Solo conozco la disponibilidad hasta el lunes 2026-10-19." in body


# 2 link before suggesting ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_friday_after_fallback_table_links_to_friday_slots_before_suggesting() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [VAGUE, VAGUE]},
        slot_prose=_failing_prose()[:3],
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("algo"))
    assert state["trace_events"][-1]["event_type"] == "slot_fallback_emitted"
    state = await workflow.handle(state, _msg("el viernes"))
    events = [e["event_type"] for e in state["trace_events"]]
    assert events[0] == "table_reply_linked"
    body = state["outbound_message"].body
    assert "2026-10-16" in body and "2026-10-15" not in body


@pytest.mark.asyncio
async def test_day_14_alone_when_model_gives_no_dates_shows_only_the_14th() -> None:
    handler = FakeConversationHandler(availability_results={"tenant": [VAGUE, VAGUE]})
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("pronto"))
    state = await workflow.handle(state, _msg("el 14"))
    body = state["outbound_message"].body
    assert "2026-10-14" in body and "2026-10-13" not in body and "2026-10-15" not in body


@pytest.mark.asyncio
async def test_weekday_outside_shown_table_is_resolved_to_its_date() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [_vague("2026-10-14", "2026-10-14"), VAGUE]}
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("el miercoles"))
    state = await workflow.handle(state, _msg("el viernes"))
    body = state["outbound_message"].body
    assert "2026-10-16" in body and "2026-10-14" not in body


# 4 bare hour inside the visit window -------------------------------------------------------


def _slot(day: str, start: str, end: str) -> OpenSlot:
    interval = TimeInterval(
        datetime.fromisoformat(f"{day}T{start}:00+02:00"),
        datetime.fromisoformat(f"{day}T{end}:00+02:00"),
    )
    return OpenSlot("S", interval, day, "Friday", start, end)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("a las 3", ["15:00"]), ("a las 10", ["09:00"]), ("a las 9", ["09:00"]), ("a las 7", [])],
)
def test_bare_hour_is_read_inside_the_visit_window(text: str, expected: list[str]) -> None:
    slots = tuple(
        _slot("2026-10-16", f"{hour:02d}:00", f"{hour + 2:02d}:00") for hour in (9, 11, 13, 15, 17)
    )
    matched = match_table_reference(slots, parse_table_reference(text))
    assert [slot.start_local for slot in matched] == expected


# 5 horizon includes the last day -----------------------------------------------------------


@pytest.mark.asyncio
async def test_table_includes_the_last_day_of_the_horizon() -> None:
    workflow = _workflow(FakeConversationHandler(availability_results={"tenant": [VAGUE]}))
    state = await workflow.handle(await started(workflow), _msg("cuando sea"))
    body = state["outbound_message"].body
    assert "2026-10-19" in body and "2026-10-20" not in body


@pytest.mark.asyncio
async def test_next_week_shows_only_the_19th_with_the_limit_phrase() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [_vague("2026-10-19", "2026-10-25")]}
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("next week"))
    body = state["outbound_message"].body
    assert "2026-10-19" in body and "2026-10-20" not in body
    assert "Solo conozco la disponibilidad hasta el lunes 2026-10-19" in body


# 7 / 11 compose facts ----------------------------------------------------------------------


def test_format_local_date_spells_the_weekday_in_each_language() -> None:
    assert format_local_date(date(2026, 10, 13), "es") == "martes 2026-10-13"
    assert format_local_date(date(2026, 10, 13), "en") == "Tuesday 2026-10-13"


@pytest.mark.asyncio
async def test_every_compose_call_gets_today_and_preformatted_dates() -> None:
    workflow, _, state = await _proposal_pending(_handler())
    handler = workflow._conversation
    assert handler.compositions and all(
        f["today"] == "2026-10-12" for _, _, f in handler.compositions
    )
    _, language, facts = handler.compositions[-1]
    assert facts["date"] == "Tuesday 2026-10-13" and facts["start"] == "09:00"
    assert state["pending_question"].action is PendingAction.TENANT_CONFIRMATION


# 9 alternatives records new availability ---------------------------------------------------


@pytest.mark.asyncio
async def test_new_availability_in_tenant_alternatives_is_recorded_and_validated() -> None:
    new = _result(_interval(10, 12, day=14))
    past = _result(_interval(10, 12, day=11))
    handler = _handler(past, new)
    workflow, _, state = await _proposal_pending(handler)
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "No, cancelo"))
    assert state["pending_question"].action is PendingAction.TENANT_ALTERNATIVES
    rejected = await workflow.handle(
        state, InboundMessage(ORDER_ID, "tenant", "también el 11 de 10 a 12")
    )
    assert rejected["trace_events"][-1]["event_type"] == "availability_rejected"
    assert rejected["pending_question"].action is PendingAction.TENANT_ALTERNATIVES
    recorded = await workflow.handle(
        rejected, InboundMessage(ORDER_ID, "tenant", "también el 14 de 10 a 12")
    )
    assert recorded["tenant_evidence"].intervals == new.intervals
    assert recorded["pending_question"].action is PendingAction.HANDYMAN_AVAILABILITY


# 10 / 12 withdrawal and hold_released ------------------------------------------------------


def _events(state: dict, name: str) -> list[dict]:
    return [e["detail"] for e in state.get("trace_events", ()) if e["event_type"] == name]


@pytest.mark.asyncio
async def test_tenant_cancel_during_handyman_confirmation_withdraws_the_proposal() -> None:
    workflow, agenda, state = await _proposal_pending(_handler())
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "yes"))
    assert state["pending_question"].action is PendingAction.HANDYMAN_CONFIRMATION
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "cancelar"))
    (extra,) = state["extra_outbound"]
    assert extra.role == "handyman"
    assert extra.body == (
        "La propuesta anterior se ha anulado. Le avisaremos si hay una nueva propuesta."
    )
    assert _events(state, "proposal_withdrawn") == [{"to_role": "handyman"}]
    assert state["pending_question"].role.value == "tenant"
    assert (await agenda.snapshot()).holds == ()
    assert not isinstance(agenda, StubAgenda)


@pytest.mark.asyncio
async def test_handyman_cancel_does_not_notify_the_handyman_again() -> None:
    workflow, _, state = await _proposal_pending(_handler())
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "yes"))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "handyman", "cancelar"))
    assert not state["extra_outbound"]
    assert _events(state, "proposal_withdrawn") == []


@pytest.mark.asyncio
async def test_hold_released_is_traced_on_cancel_and_on_reversal() -> None:
    workflow, _, state = await _proposal_pending(_handler())
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "cancel"))
    (released,) = _events(state, "hold_released")
    assert released["actor"] == "tenant" and released["interval"]["start"]

    other = _result(_interval(14, 16))
    workflow, _, state = await _proposal_pending(_handler(other))
    state = await workflow.handle(state, InboundMessage(ORDER_ID, "tenant", "mejor por la tarde"))
    (released,) = _events(state, "hold_released")
    assert released["reason"] == "availability_changed" and released["actor"] == "tenant"
