"""Dependency-injector container; this module performs no I/O."""

from pathlib import Path

from dependency_injector import containers, providers

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


class Container(containers.DeclarativeContainer):
    """Explicitly wire application components from bootstrap only."""

    settings = providers.Dependency(instance_of=Settings)
    csv_path = providers.Object(Path("/app/work_orders.csv"))
    stdin_reader = providers.Singleton(AsyncStdinReader)
    stdout_writer = providers.Singleton(AsyncStdoutWriter)
    csv_work_order_reader = providers.Factory(
        CsvWorkOrderReader,
        local_timezone=settings.provided.local_timezone,
        path=csv_path,
    )
    initialize_coordination_node = providers.Factory(InitializeCoordinationNode)
    reflect_inbound_message_node = providers.Factory(ReflectInboundMessageNode)
    coordinator = providers.Factory(
        AsyncCoordinator,
        reader=stdin_reader,
        writer=stdout_writer,
        initialize_node=initialize_coordination_node,
        inbound_node=reflect_inbound_message_node,
    )
