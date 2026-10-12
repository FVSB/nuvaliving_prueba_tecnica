"""Dependency-injector container; this module performs no I/O."""

from pathlib import Path

from dependency_injector import containers, providers

from maintenance_agent.agents.scheduling.graph import build_scheduling_graph
from maintenance_agent.agents.scheduling.nodes.initialize_coordination import (
    InitializeCoordinationNode,
)
from maintenance_agent.agents.scheduling.nodes.reflect_inbound_message import (
    ReflectInboundMessageNode,
)
from maintenance_agent.application.coordinator import AsyncCoordinator
from maintenance_agent.config import Settings
from maintenance_agent.infrastructure.cli_transport import AsyncStdinReader, AsyncStdoutWriter
from maintenance_agent.infrastructure.csv_work_orders import CsvWorkOrderReader
from maintenance_agent.infrastructure.trace_writer import RunContext, TraceWriter


class Container(containers.DeclarativeContainer):
    """Explicitly wire application components from bootstrap only."""

    settings = providers.Dependency(instance_of=Settings)
    csv_path = providers.Object(Path("/app/work_orders.csv"))
    run_context = providers.Dependency(instance_of=RunContext)
    manifest_writer = providers.Dependency(instance_of=TraceWriter)
    events_writer = providers.Dependency(instance_of=TraceWriter)
    runtime_writer = providers.Dependency(instance_of=TraceWriter)
    language_recognizer = providers.Dependency()
    stdin_reader = providers.Singleton(AsyncStdinReader)
    stdout_writer = providers.Singleton(AsyncStdoutWriter)
    csv_work_order_reader = providers.Factory(
        CsvWorkOrderReader,
        local_timezone=settings.provided.local_timezone,
        path=csv_path,
    )
    initialize_coordination_node = providers.Factory(InitializeCoordinationNode)
    reflect_inbound_message_node = providers.Factory(
        ReflectInboundMessageNode,
        trace_writer=events_writer,
    )
    scheduling_graph = providers.Factory(
        build_scheduling_graph,
        recognizer=language_recognizer,
        initialize_node=initialize_coordination_node,
        trace_writer=events_writer,
    )
    coordinator = providers.Factory(
        AsyncCoordinator,
        reader=stdin_reader,
        writer=stdout_writer,
        startup_graph=scheduling_graph,
        inbound_node=reflect_inbound_message_node,
        trace_writer=events_writer,
        runtime_writer=runtime_writer,
        manifest_writer=manifest_writer,
    )
