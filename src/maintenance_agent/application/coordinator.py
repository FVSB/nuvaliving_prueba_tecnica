"""Per-work-order sequential queues with concurrent work-order processing."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any, Protocol

from maintenance_agent.application.messages import InboundMessage, OutboundMessage
from maintenance_agent.domain.work_orders import WorkOrder
from maintenance_agent.infrastructure.cli_transport import AsyncStdoutWriter

logger = logging.getLogger("maintenance_agent.coordinator")

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
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._startup_graph = startup_graph
        self._inbound_node = inbound_node
        self._queues: dict[str, asyncio.Queue[InboundMessage]] = {}
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._all_workers: set[asyncio.Task[None]] = set()

    async def run(self, work_orders: Sequence[WorkOrder]) -> None:
        await asyncio.gather(*(self._start(work_order) for work_order in work_orders))
        async for message in self._reader.messages():
            self._dispatch(message)
        if self._all_workers:
            await asyncio.gather(*self._all_workers)

    async def _start(self, work_order: WorkOrder) -> None:
        state = await self._startup_graph.ainvoke({"work_order": work_order})
        await self._writer.write(state["outbound_message"])

    def _dispatch(self, message: InboundMessage) -> None:
        logger.info(
            "[coordinator] wo=%s node=reflect_inbound_message "
            "direction=in role=%s body=%r",
            message.work_order_id,
            message.role,
            message.body,
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
                finally:
                    queue.task_done()
        finally:
            self._workers.pop(work_order_id, None)
