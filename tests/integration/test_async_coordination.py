from datetime import datetime
from io import StringIO
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
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.work_orders import Urgency, WorkOrder
from maintenance_agent.infrastructure.cli_transport import AsyncStdoutWriter
from maintenance_agent.infrastructure.csv_work_orders import CsvWorkOrderReader

from .fakes import FakeStdinReader


def work_order() -> WorkOrder:
    return WorkOrder(
        work_order_id="WO-4",
        work_order="Water leak",
        address="Calle Mayor 18",
        description="Leak under sink",
        reported_at=datetime(2026, 10, 7, 10, 40, tzinfo=ZoneInfo("Europe/Madrid")),
        urgency=Urgency.HIGH,
    )


async def test_coordinator_starts_each_work_order_then_reflects_live_message() -> None:
    output = StringIO()
    coordinator = AsyncCoordinator(
        reader=FakeStdinReader(["WO-4|tenant Need help | urgent"]),
        writer=AsyncStdoutWriter(output),
        startup_graph=build_scheduling_graph(
            StaticLanguageRecognizer(
                LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED)
            ),
            InitializeCoordinationNode(),
        ),
        inbound_node=ReflectInboundMessageNode(),
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
