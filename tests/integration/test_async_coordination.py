from datetime import datetime
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

from maintenance_agent.agents.scheduling.graph import build_scheduling_graph
from maintenance_agent.agents.scheduling.nodes.initialize_coordination import (
    InitializeCoordinationNode,
)
from maintenance_agent.agents.scheduling.nodes.reflect_inbound_message import (
    ReflectInboundMessageNode,
)
from maintenance_agent.application.coordinator import AsyncCoordinator
from maintenance_agent.application.language_recognition import StaticLanguageRecognizer
from maintenance_agent.application.retry_queue import NoResponseRetryQueue
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.work_orders import Urgency, WorkOrder
from maintenance_agent.infrastructure.cli_transport import AsyncStdoutWriter
from maintenance_agent.infrastructure.csv_work_orders import CsvWorkOrderReader
from maintenance_agent.infrastructure.trace_writer import TraceWriter

from .fakes import FakeStdinReader


def _writer(path: Path) -> TraceWriter:
    return TraceWriter(path, "test-run", ZoneInfo("Europe/Madrid"))


def work_order() -> WorkOrder:
    return WorkOrder(
        work_order_id="WO-4",
        work_order="Water leak",
        address="Calle Mayor 18",
        description="Leak under sink",
        reported_at=datetime(2026, 10, 7, 10, 40, tzinfo=ZoneInfo("Europe/Madrid")),
        urgency=Urgency.HIGH,
    )


async def test_coordinator_starts_each_work_order_then_reflects_live_message(
    tmp_path: Path,
) -> None:
    output = StringIO()
    events = _writer(tmp_path / "events.jsonl")
    runtime = _writer(tmp_path / "runtime.jsonl")
    manifest = _writer(tmp_path / "manifest.jsonl")
    coordinator = AsyncCoordinator(
        max_message_length=2000,
        retry_queue=NoResponseRetryQueue(300.0, 3),
        retry_poll_seconds=10.0,
        reader=FakeStdinReader(["WO-4|tenant Need help | urgent"]),
        writer=AsyncStdoutWriter(output),
        startup_graph=build_scheduling_graph(
            StaticLanguageRecognizer(
                LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED)
            ),
            InitializeCoordinationNode(),
            events,
        ),
        inbound_node=ReflectInboundMessageNode(events),
        trace_writer=events,
        runtime_writer=runtime,
        manifest_writer=manifest,
    )

    await coordinator.run([work_order()])

    assert output.getvalue() == (
        "WOID:WO-4|ROLE:tenant\nNueva orden de trabajo iniciada.\n\n"
        "WOID:WO-4|ROLE:tenant\nNeed help | urgent\n\n"
    )


async def test_csv_reader_normalizes_all_rows_to_injected_timezone(tmp_path) -> None:
    source = tmp_path / "work_orders.csv"
    source.write_text(
        "work_order_id,work_order,address,description,reported_at,urgency\n"
        "WO-1,Gas leak,24 Oak Street,Gas smell,2026-10-07T07:15:00+00:00,Critical\n",
        encoding="utf-8",
    )

    work_orders = await CsvWorkOrderReader("Europe/Madrid", source).read()

    assert work_orders[0].reported_at.isoformat() == "2026-10-07T09:15:00+02:00"


async def test_coordinator_writes_language_recognition_event_to_events_jsonl(
    tmp_path: Path,
) -> None:
    output = StringIO()
    events = _writer(tmp_path / "events.jsonl")
    runtime = _writer(tmp_path / "runtime.jsonl")
    manifest = _writer(tmp_path / "manifest.jsonl")
    coordinator = AsyncCoordinator(
        max_message_length=2000,
        retry_queue=NoResponseRetryQueue(300.0, 3),
        retry_poll_seconds=10.0,
        reader=FakeStdinReader([]),
        writer=AsyncStdoutWriter(output),
        startup_graph=build_scheduling_graph(
            StaticLanguageRecognizer(LanguageRecognitionResult(language_code=LanguageCode.SPANISH)),
            InitializeCoordinationNode(),
            events,
        ),
        inbound_node=ReflectInboundMessageNode(events),
        trace_writer=events,
        runtime_writer=runtime,
        manifest_writer=manifest,
    )

    await coordinator.run([work_order()])

    payloads = events.path.read_text(encoding="utf-8").splitlines()
    assert any(
        '"event_type": "language_recognized"' in line
        and '"work_order_id": "WO-4"' in line
        and '"language_code": "es"' in line
        and "Leak under sink" in line
        for line in payloads
    )
    assert any(
        '"event_type": "initialize_coordination_entered"' in line
        and '"work_order_id": "WO-4"' in line
        for line in payloads
    )
    assert any(
        '"event_type": "initialize_coordination_completed"' in line
        and '"work_order_id": "WO-4"' in line
        and "Nueva orden de trabajo iniciada." in line
        for line in payloads
    )
    assert any('"event_type": "run_completed"' in line for line in payloads)
    assert '"event_type": "run_finished"' in manifest.path.read_text(encoding="utf-8")


async def test_coordinator_writes_inbound_dispatch_and_reflection_events(
    tmp_path: Path,
) -> None:
    output = StringIO()
    events = _writer(tmp_path / "events.jsonl")
    runtime = _writer(tmp_path / "runtime.jsonl")
    manifest = _writer(tmp_path / "manifest.jsonl")
    coordinator = AsyncCoordinator(
        max_message_length=2000,
        retry_queue=NoResponseRetryQueue(300.0, 3),
        retry_poll_seconds=10.0,
        reader=FakeStdinReader(["WO-4|tenant Need help | urgent"]),
        writer=AsyncStdoutWriter(output),
        startup_graph=build_scheduling_graph(
            StaticLanguageRecognizer(
                LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED)
            ),
            InitializeCoordinationNode(),
            events,
        ),
        inbound_node=ReflectInboundMessageNode(events),
        trace_writer=events,
        runtime_writer=runtime,
        manifest_writer=manifest,
    )

    await coordinator.run([work_order()])

    payloads = events.path.read_text(encoding="utf-8").splitlines()
    assert any(
        '"event_type": "inbound_dispatched"' in line
        and '"work_order_id": "WO-4"' in line
        and "Need help | urgent" in line
        for line in payloads
    )
    assert any(
        '"event_type": "inbound_reflected"' in line
        and '"work_order_id": "WO-4"' in line
        and "Need help | urgent" in line
        for line in payloads
    )


class _FailingInboundNode:
    async def __call__(self, message) -> object:
        raise RuntimeError("provider exploded")


async def test_inbound_node_failure_closes_order_with_requires_review_without_killing_run(
    tmp_path: Path,
) -> None:
    output = StringIO()
    events = _writer(tmp_path / "events.jsonl")
    runtime = _writer(tmp_path / "runtime.jsonl")
    manifest = _writer(tmp_path / "manifest.jsonl")
    coordinator = AsyncCoordinator(
        max_message_length=2000,
        retry_queue=NoResponseRetryQueue(300.0, 3),
        retry_poll_seconds=10.0,
        reader=FakeStdinReader(["WO-4|tenant Need help"]),
        writer=AsyncStdoutWriter(output),
        startup_graph=build_scheduling_graph(
            StaticLanguageRecognizer(
                LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED)
            ),
            InitializeCoordinationNode(),
            events,
        ),
        inbound_node=_FailingInboundNode(),
        trace_writer=events,
        runtime_writer=runtime,
        manifest_writer=manifest,
    )

    await coordinator.run([work_order()])

    text = output.getvalue()
    assert "WOID:WO-4|ROLE:tenant\nNueva orden de trabajo iniciada.\n\n" in text
    assert "WOID:WO-4|RESULT:requires_review\nERROR:RuntimeError\n" in text
    runtime_lines = runtime.path.read_text(encoding="utf-8").splitlines()
    assert any(
        '"event_type": "inbound_node_error"' in line
        and '"work_order_id": "WO-4"' in line
        and '"error_type": "RuntimeError"' in line
        for line in runtime_lines
    )
    assert '"status": "completed"' in manifest.path.read_text(encoding="utf-8")
