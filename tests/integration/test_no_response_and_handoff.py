from datetime import datetime, timezone

import pytest

from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.negotiation import TerminalStatus
from maintenance_agent.domain.work_orders import Urgency, WorkOrder
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority
from tests.integration.fakes import FakeConversationHandler


def _work_order(order_id: str) -> WorkOrder:
    return WorkOrder(
        work_order_id=order_id,
        work_order="Leak",
        address="Calle Sol 4",
        description="Water leak",
        reported_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
        urgency=Urgency.MEDIUM,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["tenant", "handyman"])
async def test_exact_no_response_closes_one_unfinished_order(role: str) -> None:
    agenda = InMemoryScheduleAuthority()
    workflow = NegotiationWorkflow(FakeConversationHandler(), agenda)
    state = await workflow.start(
        _work_order(f"WO-SILENT-{role}"),
        LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED),
    )
    order_id = state["work_order"].work_order_id
    state = await workflow.handle(state, InboundMessage(order_id, role, "<NO RESPONSE>"))
    assert state["terminal_status"] is TerminalStatus.REQUIRES_REVIEW
    assert state["terminal_frame"].detail.startswith("REASON:No response")


@pytest.mark.asyncio
async def test_near_match_does_not_close_as_no_response() -> None:
    workflow = NegotiationWorkflow(FakeConversationHandler(), InMemoryScheduleAuthority())
    state = await workflow.start(
        _work_order("WO-NEAR"),
        LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED),
    )
    state = await workflow.handle(state, InboundMessage("WO-NEAR", "tenant", "<NO RESPONSE> "))
    assert state.get("terminal_status") is None
    assert state.get("terminal_frame") is None
