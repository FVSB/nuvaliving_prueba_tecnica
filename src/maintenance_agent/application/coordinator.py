"""Per-work-order sequential queues with concurrent work-order processing."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any, Protocol

from maintenance_agent.application.messages import InboundMessage, OutboundMessage
from maintenance_agent.domain.work_orders import WorkOrder
from maintenance_agent.infrastructure.cli_transport import AsyncStdoutWriter
from maintenance_agent.infrastructure.trace_writer import TraceWriter

InboundNode = Callable[[InboundMessage], Awaitable[OutboundMessage]]


class InboundReader(Protocol):
    """Yield validated inbound messages from an injected transport."""

    def messages(self) -> AsyncIterator[InboundMessage]:
        """Return the asynchronous message stream."""


class SchedulingGraph(Protocol):
    """The compiled graph boundary required by startup coordination."""

    async def ainvoke(self, input: dict[str, Any]) -> dict[str, Any]:
        """Run a work order through the scheduling graph."""


class AsyncCoordinator:
    """Start all WOs, then keep each WO ordered while others progress concurrently."""

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
        self._queues: dict[str, asyncio.Queue[InboundMessage]] = {}
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._all_workers: set[asyncio.Task[None]] = set()

    async def run(self, work_orders: Sequence[WorkOrder]) -> None:
        status = "completed"
        try:
            await asyncio.gather(*(self._start(work_order) for work_order in work_orders))
            async for message in self._reader.messages():
                self._dispatch(message)
            if self._all_workers:
                await asyncio.gather(*self._all_workers)
            self._trace_writer.write(event_type="run_completed", detail={})
        except Exception as error:
            status = "failed"
            self._runtime_writer.write(
                event_type="run_error",
                detail={"error_type": type(error).__name__},
            )
            raise
        finally:
            self._manifest_writer.write(event_type="run_finished", detail={"status": status})

    async def _start(self, work_order: WorkOrder) -> None:
        try:
            state = await self._startup_graph.ainvoke({"work_order": work_order})
        except Exception as error:
            self._runtime_writer.write(
                event_type="startup_graph_error",
                work_order_id=work_order.work_order_id,
                detail={"error_type": type(error).__name__},
            )
            raise
        await self._writer.write(state["outbound_message"])

    def _dispatch(self, message: InboundMessage) -> None:
        self._trace_writer.write(
            event_type="inbound_dispatched",
            work_order_id=message.work_order_id,
            detail={
                "node": "reflect_inbound_message",
                "direction": "in",
                "role": message.role,
                "body": message.body,
            },
        )
        queue = self._queues.setdefault(message.work_order_id, asyncio.Queue())
        queue.put_nowait(message)
        if message.work_order_id not in self._workers:
            worker = asyncio.create_task(self._consume(message.work_order_id, queue))
            self._workers[message.work_order_id] = worker
            self._all_workers.add(worker)
            worker.add_done_callback(self._all_workers.discard)

    async def _consume(self, work_order_id: str, queue: asyncio.Queue[InboundMessage]) -> None:
        try:
            while not queue.empty():
                message = await queue.get()
                try:
                    response = await self._inbound_node(message)
                    await self._writer.write(response)
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
            self._workers.pop(work_order_id, None)
