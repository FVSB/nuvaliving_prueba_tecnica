"""Per-work-order sequential queues with concurrent work-order processing."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from maintenance_agent.application.messages import InboundMessage, OutboundMessage
from maintenance_agent.domain.work_orders import WorkOrder
from maintenance_agent.infrastructure.cli_transport import AsyncStdinReader, AsyncStdoutWriter

InboundNode = Callable[[InboundMessage], Awaitable[OutboundMessage]]
StartupNode = Callable[[WorkOrder], Awaitable[OutboundMessage]]


class AsyncCoordinator:
    """Start all WOs, then keep each WO ordered while others progress concurrently."""

    def __init__(
        self,
        reader: AsyncStdinReader,
        writer: AsyncStdoutWriter,
        initialize_node: StartupNode,
        inbound_node: InboundNode,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._initialize_node = initialize_node
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
        response = await self._initialize_node(work_order)
        await self._writer.write(response)

    def _dispatch(self, message: InboundMessage) -> None:
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
