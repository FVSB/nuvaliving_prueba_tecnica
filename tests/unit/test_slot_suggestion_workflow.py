"""T005-T006, T009, T011, T014: routing, composition, validation gate, fallback."""

import pytest

from maintenance_agent.application.conversation import (
    AmbiguityReason,
    AvailabilityInterpretation,
    PartOfDay,
    MessageClass,
    ValidationVerdict,
)
from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.negotiation import (
    GraphCursor,
    PendingAction,
    TimeInterval,
)
from tests.integration.fakes import FakeConversationHandler
from tests.unit.slot_helpers import MADRID, NOW, VAGUE, StubAgenda, appointment_at, started

from datetime import datetime


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
    assert "SLOT-20261012T0700Z" not in body  # 09:00 Madrid is occupied
    assert "SLOT-20261012T0900Z01" in body
    assert "| Slot" in body and "Spanish: intro" in body and "Spanish: ask" in body
    assert state["graph_cursor"] is GraphCursor.TENANT_AVAILABILITY
    assert state["pending_question"].action is PendingAction.TENANT_AVAILABILITY
    assert [e["event_type"] for e in state["trace_events"]] == ["slot_suggestion_attempt"]
    assert state.get("tenant_evidence") is None  # table is never evidence


@pytest.mark.asyncio
async def test_explicit_intervals_do_not_enter_slot_node() -> None:
    interval = TimeInterval(
        datetime(2026, 10, 20, 9, tzinfo=MADRID), datetime(2026, 10, 20, 12, tzinfo=MADRID)
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
    assert "trace_events" not in state


@pytest.mark.asyncio
async def test_ambiguous_relative_time_routes_to_slot_node() -> None:
    handler = FakeConversationHandler(availability_results={"tenant": [VAGUE]})
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("mañana a las 2"))
    assert len(handler.slot_compose_calls) == 1
    assert "Slot" in state["outbound_message"].body


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
async def test_validator_feedback_loops_into_next_composition() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [VAGUE]},
        slot_verdicts=[ValidationVerdict(False, "Too long"), ValidationVerdict(True, None)],
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg())
    assert handler.slot_compose_calls[0][1]["feedback"] == ""
    assert handler.slot_compose_calls[1][1]["feedback"] == "Too long"
    kinds = [e["event_type"] for e in state["trace_events"]]
    assert kinds == [
        "slot_suggestion_attempt",
        "slot_suggestion_feedback",
        "slot_suggestion_attempt",
    ]
    assert state["trace_events"][1]["detail"]["feedback"] == "Too long"
    assert "Spanish: intro" in state["outbound_message"].body


@pytest.mark.asyncio
async def test_third_failure_emits_deterministic_fallback() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [VAGUE]},
        slot_verdicts=[ValidationVerdict(False, f"bad {n}") for n in range(3)],
    )
    workflow = _workflow(handler, appointment_at(9))
    state = await workflow.handle(await started(workflow), _msg())
    assert len(handler.slot_compose_calls) == 3
    assert len(handler.slot_validate_calls) == 3
    body = state["outbound_message"].body
    assert "SLOT-" not in body and "| Slot" not in body  # fallback never names a slot
    assert "Su mensaje no indica" in body
    assert state["trace_events"][-1]["event_type"] == "slot_fallback_emitted"
    assert state["trace_events"][-1]["detail"]["ambiguity_reason"] == "other"
    assert state.get("terminal_status") is None
    assert state["pending_question"].action is PendingAction.TENANT_AVAILABILITY


@pytest.mark.asyncio
async def test_counter_resets_on_next_tenant_message() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [VAGUE, VAGUE]},
        slot_verdicts=[ValidationVerdict(False, "x")] * 3,
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg())
    state = await workflow.handle({**state, "trace_events": ()}, _msg())
    assert len(handler.slot_compose_calls) == 4  # 3 failed + 1 fresh valid
    assert "| Slot" in state["outbound_message"].body


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
    assert body.count("| SLOT-") == 1 and "2026-10-13" in body and "09:00–11:00" in body
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
        slot_verdicts=[ValidationVerdict(False, "x")] * 3,
    )
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("mañana temprano puedo"))
    assert "hora exacta" in state["outbound_message"].body


@pytest.mark.asyncio
async def test_start_of_next_week_extends_grid_beyond_seven_days() -> None:
    nxt = AvailabilityInterpretation(
        (),
        False,
        True,
        classification=MessageClass.VAGUE_DATE_REQUEST,
        date_from="2026-10-19",
        date_to="2026-10-20",
        part_of_day=PartOfDay.NONE,
    )
    handler = FakeConversationHandler(availability_results={"tenant": [nxt]})
    workflow = _workflow(handler)
    state = await workflow.handle(await started(workflow), _msg("la semana próxima a inicio"))
    body = state["outbound_message"].body
    assert body.count("| SLOT-") == 10  # 5 slots on each of Mon 19 and Tue 20
    assert "2026-10-19" in body and "2026-10-21" not in body
    assert handler.slot_compose_calls[0][1]["window"] == "2026-10-19 → 2026-10-20"
