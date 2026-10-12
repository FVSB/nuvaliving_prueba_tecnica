from pathlib import Path
from zoneinfo import ZoneInfo

from maintenance_agent.agents.scheduling.graph import build_scheduling_graph
from maintenance_agent.agents.scheduling.nodes.initialize_coordination import (
    InitializeCoordinationNode,
)
from maintenance_agent.application.language_recognition import StaticLanguageRecognizer
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.work_orders import Urgency, WorkOrder
from maintenance_agent.infrastructure.trace_writer import TraceWriter


def work_order(description: str) -> WorkOrder:
    return WorkOrder.model_validate(
        {
            "work_order_id": "WO-1",
            "work_order": "Leak",
            "address": "1 Main Street",
            "description": description,
            "reported_at": "2026-10-07T09:15:00+02:00",
            "urgency": Urgency.HIGH,
        }
    )


def _trace_writer(tmp_path: Path) -> TraceWriter:
    return TraceWriter(tmp_path / "events.jsonl", "test-run", ZoneInfo("Europe/Madrid"))


async def test_graph_recognizes_language_before_initial_message(tmp_path: Path) -> None:
    graph = build_scheduling_graph(
        recognizer=StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.SPANISH)
        ),
        initialize_node=InitializeCoordinationNode(),
        trace_writer=_trace_writer(tmp_path),
    )

    result = await graph.ainvoke({"work_order": work_order("Hay una fuga de agua.")})

    assert result["language_recognition"].language_code is LanguageCode.SPANISH
    assert result["outbound_message"].role == "tenant"


async def test_graph_retains_undetermined_result(tmp_path: Path) -> None:
    graph = build_scheduling_graph(
        recognizer=StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED)
        ),
        initialize_node=InitializeCoordinationNode(),
        trace_writer=_trace_writer(tmp_path),
    )

    result = await graph.ainvoke({"work_order": work_order("12345 !!!")})

    assert result["language_recognition"].language_code is LanguageCode.UNDETERMINED


async def test_graph_recognizes_english_before_initial_message(tmp_path: Path) -> None:
    graph = build_scheduling_graph(
        recognizer=StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
        ),
        initialize_node=InitializeCoordinationNode(),
        trace_writer=_trace_writer(tmp_path),
    )

    result = await graph.ainvoke({"work_order": work_order("Water is leaking under the sink.")})

    assert result["language_recognition"].language_code is LanguageCode.ENGLISH
    assert result["outbound_message"].role == "tenant"
