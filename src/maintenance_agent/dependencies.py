"""Dependency-injector container; this module performs no I/O."""

from pathlib import Path

from dependency_injector import containers, providers

from maintenance_agent.agents.scheduling.graph import build_scheduling_graph
from maintenance_agent.agents.scheduling.nodes.initialize_coordination import (
    InitializeCoordinationNode,
)
from maintenance_agent.agents.scheduling.nodes.injection_guard import InjectionGuardNode
from maintenance_agent.agents.scheduling.nodes.reflect_inbound_message import (
    ReflectInboundMessageNode,
)
from maintenance_agent.application.coordinator import AsyncCoordinator
from maintenance_agent.application.injection_guard import InjectionGuard
from maintenance_agent.application.slot_table import SlotGridSpec
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.config import Settings
from maintenance_agent.infrastructure.cli_transport import AsyncStdinReader, AsyncStdoutWriter
from maintenance_agent.infrastructure.csv_work_orders import CsvWorkOrderReader
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority
from maintenance_agent.infrastructure.trace_writer import RunContext, TraceWriter


def _build_guard_node(
    guard: InjectionGuard | None, trace_writer: TraceWriter, runtime_writer: TraceWriter
) -> InjectionGuardNode | None:
    """Wire the guard node only when a guard exists (an Anthropic key was configured)."""
    return None if guard is None else InjectionGuardNode(guard, trace_writer, runtime_writer)


class Container(containers.DeclarativeContainer):
    """Explicitly wire application components from bootstrap only."""

    settings = providers.Dependency(instance_of=Settings)
    csv_path = providers.Object(Path("/app/work_orders.csv"))
    clock = providers.Object(None)
    run_context = providers.Dependency(instance_of=RunContext)
    manifest_writer = providers.Dependency(instance_of=TraceWriter)
    events_writer = providers.Dependency(instance_of=TraceWriter)
    runtime_writer = providers.Dependency(instance_of=TraceWriter)
    language_recognizer = providers.Dependency()
    conversation_handler = providers.Dependency()
    injection_guard = providers.Object(None)
    schedule_authority = providers.Singleton(InMemoryScheduleAuthority)
    stdin_reader = providers.Singleton(
        AsyncStdinReader,
        runtime_writer=runtime_writer,
        max_message_length=settings.provided.max_message_length,
    )
    stdout_writer = providers.Singleton(AsyncStdoutWriter)
    csv_work_order_reader = providers.Factory(
        CsvWorkOrderReader,
        local_timezone=settings.provided.local_timezone,
        path=csv_path,
    )
    initialize_coordination_node = providers.Factory(InitializeCoordinationNode)
    slot_grid = providers.Factory(
        SlotGridSpec,
        lookahead_days=settings.provided.slot_lookahead_days,
        daily_start_hour=settings.provided.slot_daily_start_hour,
        daily_end_hour=settings.provided.slot_daily_end_hour,
        slot_hours=settings.provided.slot_hours,
    )
    negotiation_workflow = providers.Factory(
        NegotiationWorkflow,
        conversation=conversation_handler,
        agenda=schedule_authority,
        local_timezone=settings.provided.local_timezone,
        clock=clock,
        slot_grid=slot_grid,
        visit_horizon_days=settings.provided.visit_horizon_days,
    )
    reflect_inbound_message_node = providers.Factory(
        ReflectInboundMessageNode,
        trace_writer=events_writer,
    )
    injection_guard_node = providers.Callable(
        _build_guard_node,
        guard=injection_guard,
        trace_writer=events_writer,
        runtime_writer=runtime_writer,
    )
    scheduling_graph = providers.Factory(
        build_scheduling_graph,
        recognizer=language_recognizer,
        initialize_node=initialize_coordination_node,
        trace_writer=events_writer,
        workflow=negotiation_workflow,
        guard_node=injection_guard_node,
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
        max_message_length=settings.provided.max_message_length,
    )
