"""T005-T006, T009, T011, T014: routing, composition, validation gate, fallback."""

from datetime import datetime

import pytest

from maintenance_agent.application.conversation import (
    AmbiguityReason,
    AvailabilityInterpretation,
    MessageClass,
    PartOfDay,
)
from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.negotiation import (
    GraphCursor,
    PendingAction,
    TimeInterval,
)
from tests.integration.fakes import BAD_PROSE, FakeConversationHandler
from tests.unit.slot_helpers import MADRID, NOW, VAGUE, StubAgenda, appointment_at, started


def _workflow(handler: FakeConversationHandler, *appointments) -> NegotiationWorkflow:
    return NegotiationWorkflow(
        handler, StubAgenda(*appointments), "Europe/Madrid", clock=lambda: NOW
    )


def _msg(text: str = "esta semana por la tarde que dias?") -> InboundMessage:
    return InboundMessage("WO-S1", "tenant", text)


@pytest.mark.asyncio
async def test_vague_request_replies_with_deterministic_table() -> None:
    handler = FakeConversationHandler(availability_results={"tenant": [VAGUE]})
    workflow = _workflow(handler, appointment_at(9))
    state = await workflow.handle(await started(workflow), _msg())
    body = state["outbound_message"].body
    assert "| 2026-10-12   | Monday     | 09:00–11:00" not in body  # 09:00 Madrid is occupied
    assert "11:00–13:00" in body and "SLOT-" not in body
    assert "| Date" in body and "Spanish: intro" in body and "Spanish: ask" in body
    assert state["graph_cursor"] is GraphCursor.TENANT_AVAILABILITY
    assert state["pending_question"].action is PendingAction.TENANT_AVAILABILITY
    assert [e["event_type"] for e in state["trace_events"]] == ["slot_suggestion_attempt"]
    assert state.get("tenant_evidence") is None  # table is never evidence


@pytest.mark.asyncio
async def test_explicit_intervals_do_not_enter_slot_node() -> None:
    interval = TimeInterval(
        datetime(2026, 10, 14, 9, tzinfo=MADRID), datetime(2026, 10, 14, 12, tzinfo=MADRID)
    )
    result = AvailabilityInterpretation(
        (interval,), True, False, classification=MessageClass.EXPLICIT_INTERVALS
    )
    handler = FakeConversationHandler(availability_results={"tenant": [result]})
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("el 20 de 9 a 12"))
    assert handler.slot_compose_calls == []
    assert state["tenant_evidence"].intervals == (interval,)


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [MessageClass.DECISION, MessageClass.UNCLASSIFIED])
async def test_decision_or_unclassified_keeps_clarification(cls: MessageClass) -> None:
    result = AvailabilityInterpretation((), False, True, classification=cls)
    handler = FakeConversationHandler(availability_results={"tenant": [result]})
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("si"))
    assert handler.slot_compose_calls == []
    assert any(c[0] == "clarify_absolute_availability" for c in handler.compositions)
    assert not state.get("trace_events")


@pytest.mark.asyncio
async def test_ambiguous_relative_time_routes_to_slot_node() -> None:
    handler = FakeConversationHandler(availability_results={"tenant": [VAGUE]})
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("mañana a las 2"))
    assert len(handler.slot_compose_calls) == 1
    assert "| Date" in state["outbound_message"].body


@pytest.mark.asyncio
async def test_unambiguous_relative_time_keeps_confirmation_path() -> None:
    suggestion = TimeInterval(
        datetime(2026, 10, 13, 14, tzinfo=MADRID), datetime(2026, 10, 13, 16, tzinfo=MADRID)
    )
    result = AvailabilityInterpretation(
        (),
        True,
        False,
        (suggestion,),
        True,
        classification=MessageClass.EXPLICIT_INTERVALS,
    )
    handler = FakeConversationHandler(availability_results={"tenant": [result]})
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("mañana a las 2 de la tarde"))
    assert handler.slot_compose_calls == []
    assert state["pending_question"].action is PendingAction.RELATIVE_DATE_CONFIRMATION


@pytest.mark.asyncio
async def test_prose_feedback_loops_into_next_composition() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [VAGUE]}, slot_prose=[BAD_PROSE]
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg())
    assert handler.slot_compose_calls[0][1]["feedback"] == ""
    feedback = handler.slot_compose_calls[1][1]["feedback"]
    assert "promise or guarantee" in feedback
    kinds = [e["event_type"] for e in state["trace_events"]]
    assert kinds == [
        "slot_suggestion_attempt",
        "slot_suggestion_feedback",
        "slot_suggestion_attempt",
    ]
    assert state["trace_events"][1]["detail"]["feedback"] == feedback
    assert "Spanish: intro" in state["outbound_message"].body


@pytest.mark.asyncio
async def test_third_failure_emits_deterministic_fallback() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [VAGUE]},
        slot_prose=[BAD_PROSE] * 3,
    )
    workflow = _workflow(handler, appointment_at(9))
    state = await workflow.handle(await started(workflow), _msg())
    assert len(handler.slot_compose_calls) == 3
    body = state["outbound_message"].body
    assert "SLOT-" not in body and "| Date" in body  # fixed text plus the deterministic table
    assert "Su mensaje no indica" in body
    assert state["slot_table_request"] is not None  # the table is linkable afterwards
    assert state["trace_events"][-1]["event_type"] == "slot_fallback_emitted"
    assert state["trace_events"][-1]["detail"]["ambiguity_reason"] == "other"
    assert state.get("terminal_status") is None
    assert state["pending_question"].action is PendingAction.TENANT_AVAILABILITY


@pytest.mark.asyncio
async def test_counter_resets_on_next_tenant_message() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [VAGUE, VAGUE]},
        slot_prose=[BAD_PROSE] * 3,
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg())
    state = await workflow.handle({**state, "trace_events": ()}, _msg())
    assert len(handler.slot_compose_calls) == 4  # 3 failed + 1 fresh valid
    assert "| Date" in state["outbound_message"].body


@pytest.mark.asyncio
async def test_provider_error_counts_as_failed_attempt() -> None:
    class Broken(FakeConversationHandler):
        async def compose_slot_reply(self, language, facts):
            raise RuntimeError("down")

    handler = Broken(availability_results={"tenant": [VAGUE]})
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg())
    assert state["trace_events"][-1]["event_type"] == "slot_fallback_emitted"


@pytest.mark.asyncio
async def test_tomorrow_early_resolves_to_tomorrow_morning_slots_only() -> None:
    early = AvailabilityInterpretation(
        (),
        False,
        True,
        classification=MessageClass.VAGUE_DATE_REQUEST,
        date_from="2026-10-13",
        date_to="2026-10-13",
        part_of_day=PartOfDay.MORNING,
        ambiguity_reason=AmbiguityReason.UNSPECIFIED_TIME,
    )
    handler = FakeConversationHandler(availability_results={"tenant": [early]})
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("mañana temprano puedo"))
    body = state["outbound_message"].body
    assert body.count("| 2026-10-") == 1 and "2026-10-13" in body and "09:00–11:00" in body
    assert "2026-10-12" not in body  # today is not offered
    assert handler.slot_compose_calls[0][1]["window"] == "2026-10-13, mañana (hasta las 12:00)"


@pytest.mark.asyncio
async def test_fallback_explains_why_the_request_was_ambiguous() -> None:
    early = AvailabilityInterpretation(
        (),
        False,
        True,
        classification=MessageClass.VAGUE_DATE_REQUEST,
        ambiguity_reason=AmbiguityReason.UNSPECIFIED_TIME,
    )
    handler = FakeConversationHandler(
        availability_results={"tenant": [early]},
        slot_prose=[BAD_PROSE] * 3,
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("mañana temprano puedo"))
    assert "hora exacta" in state["outbound_message"].body


def _window(date_from: str, date_to: str) -> AvailabilityInterpretation:
    return AvailabilityInterpretation(
        (),
        False,
        True,
        classification=MessageClass.VAGUE_DATE_REQUEST,
        date_from=date_from,
        date_to=date_to,
        part_of_day=PartOfDay.NONE,
    )


LIMIT = "Solo conozco la disponibilidad hasta el lunes 2026-10-19."


@pytest.mark.asyncio
async def test_window_inside_the_horizon_extends_grid_without_limit_note() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [_window("2026-10-16", "2026-10-19")]}
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("hasta el lunes"))
    body = state["outbound_message"].body
    assert body.count("| 2026-10-") == 20  # 5 slots on each of Fri 16, Sat 17, Sun 18, Mon 19
    assert LIMIT not in body


@pytest.mark.asyncio
async def test_window_partly_beyond_the_horizon_shows_only_known_days_and_the_limit() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [_window("2026-10-19", "2026-10-20")]}
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("la semana próxima a inicio"))
    body = state["outbound_message"].body
    assert body.count("| 2026-10-") == 5
    assert "2026-10-19" in body and "2026-10-20" not in body
    assert LIMIT in body and "fecha dentro de ese límite" in body


@pytest.mark.asyncio
async def test_window_entirely_beyond_the_horizon_states_the_limit_without_a_table() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [_window("2026-10-26", "2026-10-27")]}
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("dentro de dos semanas"))
    body = state["outbound_message"].body
    assert body == (
        "Solo conozco la disponibilidad hasta el lunes 2026-10-19. "
        "Indíqueme una fecha dentro de ese límite."
    )
    assert "| 2026-10-" not in body and handler.slot_compose_calls == []
    assert state["pending_question"].action is PendingAction.TENANT_AVAILABILITY
    assert state["trace_events"][0]["event_type"] == "slot_window_beyond_horizon"


@pytest.mark.asyncio
async def test_taken_time_offers_open_slots_instead_of_reasking() -> None:
    taken = appointment_at(9, day=13)
    handler = FakeConversationHandler(
        availability_results={
            "tenant": [AvailabilityInterpretation((taken.interval,), True, False)]
        }
    )
    workflow = _workflow(handler, taken)
    state = await workflow.handle(await started(workflow), _msg("mañana a las 9am"))
    body = state["outbound_message"].body
    assert body.startswith(
        "Ese horario ya no está disponible: está reservado para otra visita confirmada."
    )
    assert "| Date" in body and "SLOT-" not in body
    assert "| 2026-10-13   | Tuesday    | 09:00–11:00" not in body
    assert state["pending_question"].action is PendingAction.TENANT_AVAILABILITY
    assert state.get("tenant_evidence") is None


@pytest.mark.asyncio
async def test_wrong_language_is_translated_and_rechecked() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [VAGUE]}, detected_languages=["english", "spanish"]
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg())
    assert len(handler.detect_calls) == 2
    assert [call[1] for call in handler.translate_calls] == ["Spanish", "Spanish"]
    events = state["trace_events"]
    translated = next(e for e in events if e["event_type"] == "slot_reply_translated")
    assert translated["detail"] == {
        "actor": "system",
        "expected_language": "spanish",
        "translations": 1,
    }
    assert not any(e["event_type"] == "slot_fallback_emitted" for e in events)
    assert "| Date" in state["outbound_message"].body or "| Fecha" in state["outbound_message"].body


@pytest.mark.asyncio
async def test_language_cycle_is_capped_and_traces_expected_and_detected() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [VAGUE]}, detected_languages=["english"] * 4
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg())
    assert len(handler.detect_calls) == 4  # first check plus three translate-and-check cycles
    assert len(handler.translate_calls) == 6  # intro and ask, three times
    mismatch = next(
        e for e in state["trace_events"] if e["event_type"] == "slot_reply_language_mismatch"
    )
    assert mismatch["detail"]["expected_language"] == "spanish"
    assert mismatch["detail"]["detected_language"] == "english"
    assert "3 translate-and-check cycles" in mismatch["detail"]["reason"]
    # The reply still goes out (as is) with the deterministic table, not the fixed fallback.
    assert "Spanish: intro" in state["outbound_message"].body
    assert not any(e["event_type"] == "slot_fallback_emitted" for e in state["trace_events"])


@pytest.mark.asyncio
async def test_language_detection_failure_is_traced_and_reply_still_sent() -> None:
    class Broken(FakeConversationHandler):
        async def detect_language(self, text):
            raise RuntimeError("down")

    handler = Broken(availability_results={"tenant": [VAGUE]})
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg())
    mismatch = next(
        e for e in state["trace_events"] if e["event_type"] == "slot_reply_language_mismatch"
    )
    assert mismatch["detail"]["reason"] == "language detection failed: RuntimeError"
    assert "Spanish: intro" in state["outbound_message"].body


@pytest.mark.asyncio
async def test_vague_weekday_in_alternatives_is_answered_from_the_agenda() -> None:
    handler = FakeConversationHandler(availability_results={"tenant": [VAGUE]})
    workflow = _workflow(handler)
    state = await started(workflow)
    state = {
        **state,
        "pending_question": workflow._question(
            state["pending_question"].role, PendingAction.TENANT_ALTERNATIVES
        ),
    }
    state = await workflow.handle(state, _msg("puede ser el sábado?"))
    body = state["outbound_message"].body
    assert "| 2026-10-17" in body and "2026-10-13" not in body  # only Saturday is listed
    assert not any(c[0] == "clarify_tenant_alternatives" for c in handler.compositions)
    assert state["pending_question"].action is PendingAction.TENANT_AVAILABILITY
