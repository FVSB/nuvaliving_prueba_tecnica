"""Invalid dates or hours are refused with a reason, a trace event and no evidence."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from maintenance_agent.application.conversation import AvailabilityInterpretation
from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.date_validation import DateCheck, DateErrorCode
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.negotiation import PendingAction, TimeInterval
from maintenance_agent.domain.work_orders import Urgency, WorkOrder
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority
from tests.integration.fakes import FakeConversationHandler

MADRID = ZoneInfo("Europe/Madrid")
NOW = datetime(2026, 10, 12, 12, tzinfo=MADRID)
ORDER_ID = "WO-REJ"


def _interval(day: int, start_hour: int, end_hour: int, year: int = 2026) -> TimeInterval:
    return TimeInterval(
        datetime(year, 10, day, start_hour, tzinfo=MADRID),
        datetime(year, 10, day, end_hour, tzinfo=MADRID),
    )


def _order() -> WorkOrder:
    return WorkOrder(
        work_order_id=ORDER_ID,
        work_order="Leak",
        address="Calle Sol 4",
        description="Water leak",
        reported_at=datetime(2026, 10, 12, tzinfo=MADRID),
        urgency=Urgency.HIGH,
    )


def _workflow(handler: FakeConversationHandler) -> NegotiationWorkflow:
    return NegotiationWorkflow(handler, InMemoryScheduleAuthority(), clock=lambda: NOW)


async def _started(workflow: NegotiationWorkflow) -> dict:
    return await workflow.start(
        _order(), LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
    )


async def _awaiting_handyman() -> tuple[NegotiationWorkflow, FakeConversationHandler, dict]:
    handler = FakeConversationHandler(
        availability_results={
            "tenant": [AvailabilityInterpretation((_interval(13, 9, 13),), True, False)]
        }
    )
    workflow = _workflow(handler)
    state = await workflow.handle(
        await _started(workflow), InboundMessage(ORDER_ID, "tenant", "13th 9 to 13")
    )
    assert state["pending_question"].action is PendingAction.HANDYMAN_AVAILABILITY
    return workflow, handler, state


def _rejection(state: dict) -> dict:
    events = [e for e in state["trace_events"] if e["event_type"] == "availability_rejected"]
    assert len(events) == 1
    return events[0]["detail"]


@pytest.mark.asyncio
async def test_tenant_invalid_reason_is_refused_with_reason_and_trace() -> None:
    check = DateCheck(
        False,
        DateErrorCode.WEEKDAY_MISMATCH,
        "2026-10-16 is a Friday, not a Thursday.",
        "Friday",
        "2026-10-15",
    )
    handler = FakeConversationHandler(
        availability_results={
            "tenant": [AvailabilityInterpretation((), False, True, invalid_reason=check)]
        }
    )
    workflow = _workflow(handler)
    before = await _started(workflow)
    state = await workflow.handle(before, InboundMessage(ORDER_ID, "tenant", "jueves 16"))
    assert state.get("tenant_evidence") is None
    assert state["pending_question"] == before["pending_question"]
    assert state["graph_cursor"] == before["graph_cursor"]
    assert _rejection(state) == {
        "actor": "tenant",
        "code": "weekday_mismatch",
        "reason": check.reason,
        "input": "jueves 16",
        "proposed": "2026-10-15",
    }
    intent, language, facts = handler.compositions[-1]
    assert (intent, language) == ("reject_invalid_availability", "English")
    assert facts["reason"] == check.reason and facts["nearest_valid"] == "Thursday 2026-10-15"
    assert facts["code"] == "weekday_mismatch" and check.reason in facts["instruction"]
    assert state["outbound_message"].role == "tenant"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("interval", "code"),
    [
        (_interval(13, 3, 5), "outside_visit_hours"),
        (_interval(13, 9, 11, year=2062), "too_far_ahead"),
        (_interval(11, 9, 11), "in_the_past"),
    ],
)
async def test_tenant_backstop_refuses_intervals_the_model_let_through(
    interval: TimeInterval, code: str
) -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [AvailabilityInterpretation((interval,), True, False)]}
    )
    workflow = _workflow(handler)
    state = await workflow.handle(
        await _started(workflow), InboundMessage(ORDER_ID, "tenant", "some text")
    )
    assert state.get("tenant_evidence") is None
    assert state["pending_question"].action is PendingAction.TENANT_AVAILABILITY
    assert _rejection(state)["code"] == code
    assert _rejection(state)["input"] == "some text"
    assert handler.compositions[-1][0] == "reject_invalid_availability"


@pytest.mark.asyncio
async def test_handyman_invalid_reason_is_refused_in_spanish_without_evidence() -> None:
    workflow, handler, awaiting = await _awaiting_handyman()
    check = DateCheck(False, DateErrorCode.OUTSIDE_VISIT_HOURS, "03:00 is outside 09:00-19:00.")
    handler.availability_results["handyman"] = [
        AvailabilityInterpretation((), False, True, invalid_reason=check)
    ]
    state = await workflow.handle(awaiting, InboundMessage(ORDER_ID, "handyman", "a las 3"))
    assert state.get("handyman_evidence") is None
    assert state["pending_question"] == awaiting["pending_question"]
    assert _rejection(state)["actor"] == "handyman"
    assert _rejection(state)["proposed"] is None
    assert handler.compositions[-1][:2] == ("reject_invalid_availability", "Spanish")
    assert state["outbound_message"].role == "handyman"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("interval", "code"),
    [(_interval(13, 3, 5), "outside_visit_hours"), (_interval(13, 9, 11, 2062), "too_far_ahead")],
)
async def test_handyman_backstop_refuses_03_00_and_2062(interval: TimeInterval, code: str) -> None:
    workflow, handler, awaiting = await _awaiting_handyman()
    handler.availability_results["handyman"] = [
        AvailabilityInterpretation((interval,), True, False)
    ]
    state = await workflow.handle(awaiting, InboundMessage(ORDER_ID, "handyman", "text"))
    assert state.get("handyman_evidence") is None
    assert state["pending_question"] == awaiting["pending_question"]
    assert _rejection(state)["code"] == code


@pytest.mark.asyncio
async def test_empty_interpretation_without_reason_keeps_generic_clarification() -> None:
    handler = FakeConversationHandler(
        availability_results={"tenant": [AvailabilityInterpretation((), False, True)]}
    )
    workflow = _workflow(handler)
    state = await workflow.handle(
        await _started(workflow), InboundMessage(ORDER_ID, "tenant", "hm")
    )
    assert handler.compositions[-1][0] == "clarify_absolute_availability"
    assert not state.get("trace_events")


@pytest.mark.asyncio
async def test_valid_interval_still_reaches_the_handyman() -> None:
    _, _, state = await _awaiting_handyman()
    assert state["tenant_evidence"].intervals[0].end - state["tenant_evidence"].intervals[
        0
    ].start == timedelta(hours=4)


@pytest.mark.asyncio
async def test_too_far_ahead_names_the_last_known_date_with_its_weekday() -> None:
    handler = FakeConversationHandler(
        availability_results={
            "tenant": [AvailabilityInterpretation((_interval(13, 9, 11, 2062),), True, False)]
        }
    )
    workflow = _workflow(handler)
    await workflow.handle(await _started(workflow), InboundMessage(ORDER_ID, "tenant", "2062"))
    _, _, facts = handler.compositions[-1]
    assert facts["last_known_date"] == "Monday 2026-10-19"
    assert "only know the availability until Monday 2026-10-19" in facts["instruction"]
