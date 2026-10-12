"""Per-work-order queues, retained graph state and concurrent independent orders."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from maintenance_agent.application.messages import InboundMessage, OutboundMessage
from maintenance_agent.domain.work_orders import WorkOrder
from maintenance_agent.infrastructure.cli_transport import AsyncStdoutWriter
from maintenance_agent.infrastructure.trace_writer import TraceWriter

InboundNode = Callable[[InboundMessage], Awaitable[OutboundMessage]]


@dataclass(frozen=True, slots=True)
class DisplacedHoldEvent:
    work_order_id: str


CoordinatorEvent = InboundMessage | DisplacedHoldEvent


class InboundReader(Protocol):
    def messages(self) -> AsyncIterator[InboundMessage]: ...


class SchedulingGraph(Protocol):
    async def ainvoke(self, input: dict[str, Any]) -> dict[str, Any]: ...


class AsyncCoordinator:
    """Start all orders, serialize each order's event stream, and retain graph state."""

    def __init__(
        self,
        reader: InboundReader,
        writer: AsyncStdoutWriter,
        startup_graph: SchedulingGraph,
        inbound_node: InboundNode,
        trace_writer: TraceWriter,
        runtime_writer: TraceWriter,
        manifest_writer: TraceWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._startup_graph = startup_graph
        self._inbound_node = inbound_node
        self._trace_writer = trace_writer
        self._runtime_writer = runtime_writer
        self._manifest_writer = manifest_writer
        self._queues: dict[str, asyncio.Queue[CoordinatorEvent]] = {}
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._all_workers: set[asyncio.Task[None]] = set()
        self._states: dict[str, dict[str, Any]] = {}

    async def run(self, work_orders: Sequence[WorkOrder]) -> None:
        status = "completed"
        try:
            self._trace_writer.write(
                event_type="work_orders_starting", detail={"count": len(work_orders)}
            )
            await asyncio.gather(*(self._start(work_order) for work_order in work_orders))
            self._trace_writer.write(
                event_type="work_orders_started", detail={"count": len(work_orders)}
            )
            async for message in self._reader.messages():
                self._dispatch(message)
            if self._all_workers:
                await asyncio.gather(*self._all_workers)
            self._trace_writer.write(event_type="run_completed", detail={})
        except Exception as error:
            status = "failed"
            self._runtime_writer.write(
                event_type="run_error", detail={"error_type": type(error).__name__}
            )
            raise
        finally:
            self._manifest_writer.write(event_type="run_finished", detail={"status": status})

    async def _start(self, work_order: WorkOrder) -> None:
        try:
            self._trace_writer.write(
                event_type="work_order_start_entered",
                work_order_id=work_order.work_order_id,
                detail={},
            )
            state = await self._startup_graph.ainvoke({"work_order": work_order})
            self._trace_writer.write(
                event_type="work_order_start_completed",
                work_order_id=work_order.work_order_id,
                detail={},
            )
        except Exception as error:
            self._runtime_writer.write(
                event_type="startup_graph_error",
                work_order_id=work_order.work_order_id,
                detail={"error_type": type(error).__name__},
            )
            raise
        self._states[work_order.work_order_id] = state
        await self._deliver_state(work_order.work_order_id, state)

    def _dispatch(self, message: InboundMessage) -> None:
        self._trace_writer.write(
            event_type="inbound_dispatched",
            work_order_id=message.work_order_id,
            detail={
                "node": "negotiation_transition",
                "direction": "in",
                "role": message.role,
                "body": message.body,
            },
        )
        self._enqueue(message.work_order_id, message)

    def _enqueue(self, work_order_id: str, event: CoordinatorEvent) -> None:
        queue = self._queues.setdefault(work_order_id, asyncio.Queue())
        queue.put_nowait(event)
        if work_order_id not in self._workers:
            worker = asyncio.create_task(self._consume(work_order_id, queue))
            self._workers[work_order_id] = worker
            self._all_workers.add(worker)
            worker.add_done_callback(self._all_workers.discard)

    async def _consume(self, work_order_id: str, queue: asyncio.Queue[CoordinatorEvent]) -> None:
        self._trace_writer.write(
            event_type="order_worker_started", work_order_id=work_order_id, detail={}
        )
        try:
            while not queue.empty():
                event = await queue.get()
                try:
                    current = self._states.get(work_order_id)
                    if current is not None and "graph_cursor" in current:
                        graph_input = {**current, "resume_finalization": False}
                        if isinstance(event, DisplacedHoldEvent):
                            graph_input["displaced_hold_event"] = True
                        else:
                            graph_input["inbound_message"] = event
                        result = await self._startup_graph.ainvoke(graph_input)
                    else:
                        if isinstance(event, DisplacedHoldEvent):
                            continue
                        response = await self._inbound_node(event)
                        result = {"outbound_message": response}
                    await self._deliver_state(work_order_id, result, previous=current)
                    self._trace_writer.write(
                        event_type="order_transition_delivered",
                        work_order_id=work_order_id,
                        detail={},
                    )
                    for displaced_id in result.get("displaced_work_orders", ()):
                        self._enqueue(displaced_id, DisplacedHoldEvent(displaced_id))
                    await self._continue_finalization(work_order_id)
                except Exception as error:
                    self._runtime_writer.write(
                        event_type="inbound_node_error",
                        work_order_id=work_order_id,
                        detail={"error_type": type(error).__name__},
                    )
                    raise
                finally:
                    queue.task_done()
        finally:
            self._trace_writer.write(
                event_type="order_worker_finished", work_order_id=work_order_id, detail={}
            )
            self._workers.pop(work_order_id, None)

    async def _deliver_state(
        self, work_order_id: str, state: dict[str, Any], previous: dict[str, Any] | None = None
    ) -> None:
        outbound = state.get("outbound_message")
        terminal = state.get("terminal_frame")
        if outbound is not None:
            await self._writer.write(outbound)
        if terminal is not None:
            await self._writer.write_terminal(terminal)
        saved = dict(state)
        saved["outbound_message"] = None
        saved["terminal_frame"] = None
        saved["inbound_message"] = None
        saved["resume_finalization"] = False
        saved["displaced_hold_event"] = False
        saved["displaced_work_orders"] = ()
        self._states[work_order_id] = saved

    async def _continue_finalization(self, work_order_id: str) -> None:
        while True:
            state = self._states.get(work_order_id)
            if state is None or not state.get("finalization_pending"):
                return
            result = await self._startup_graph.ainvoke({**state, "resume_finalization": True})
            await self._deliver_state(work_order_id, result, previous=state)
            if result.get("terminal_frame") is not None or not result.get("outbound_message"):
                return
