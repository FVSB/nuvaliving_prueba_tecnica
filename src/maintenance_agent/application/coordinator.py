"""Per-work-order queues, retained graph state and concurrent independent orders."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from maintenance_agent.application.conversation import AmbiguityReason
from maintenance_agent.application.messages import (
    InboundMessage,
    OutboundMessage,
    RejectedInbound,
)
from maintenance_agent.application.outbound_guard import leaks_internal_identifier
from maintenance_agent.application.rejections import (
    RejectionReason,
    preview,
    render_rejection,
)
from maintenance_agent.application.slot_table import render_slot_fallback_reply
from maintenance_agent.domain.work_orders import WorkOrder
from maintenance_agent.infrastructure.cli_transport import AsyncStdoutWriter
from maintenance_agent.infrastructure.trace_writer import TraceWriter

InboundNode = Callable[[InboundMessage], Awaitable[OutboundMessage]]


@dataclass(frozen=True, slots=True)
class DisplacedHoldEvent:
    work_order_id: str


CoordinatorEvent = InboundMessage | RejectedInbound | DisplacedHoldEvent


class InboundReader(Protocol):
    def messages(self) -> AsyncIterator[InboundMessage | RejectedInbound]: ...


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
        max_message_length: int = 2000,
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
        self._known_ids: frozenset[str] = frozenset()
        self._completed_ids: set[str] = set()
        self._max_message_length = max_message_length

    async def run(self, work_orders: Sequence[WorkOrder]) -> None:
        status = "completed"
        self._known_ids = frozenset(order.work_order_id for order in work_orders)
        try:
            self._trace_writer.write(
                event_type="work_orders_starting", detail={"count": len(work_orders)}
            )
            await asyncio.gather(*(self._start(work_order) for work_order in work_orders))
            self._trace_writer.write(
                event_type="work_orders_started", detail={"count": len(work_orders)}
            )
            async for message in self._reader.messages():
                if isinstance(message, RejectedInbound):
                    if message.work_order_id in self._known_ids:
                        self._enqueue(message.work_order_id, message)
                    else:
                        await self._reject(message)
                elif message.work_order_id not in self._known_ids:
                    await self._reject(
                        RejectedInbound(
                            message.work_order_id,
                            message.role,
                            RejectionReason.UNKNOWN_WORK_ORDER,
                            len(message.body),
                            preview(message.body),
                            self._max_message_length,
                        )
                    )
                else:
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

    async def _reject(self, rejected: RejectedInbound) -> None:
        """Trace the rejection and answer the sender with a fixed, content-free notice."""
        if rejected.work_order_id in self._completed_ids:
            return
        reason = rejected.reason
        if rejected.work_order_id not in self._known_ids:
            reason = RejectionReason.UNKNOWN_WORK_ORDER
            self._trace_writer.write(
                event_type="unknown_work_order",
                detail={
                    "sent_work_order_id": rejected.work_order_id,
                    "role": rejected.role,
                    "length": rejected.length,
                },
            )
        self._trace_writer.write(
            event_type="message_rejected",
            detail={
                "reason": reason,
                "sent_work_order_id": rejected.work_order_id,
                "role": rejected.role,
                "length": rejected.length,
                "body_preview": rejected.preview,
            },
        )
        state = self._states.get(rejected.work_order_id) or {}
        language = (
            "es"
            if rejected.role == "handyman"
            else str(state.get("tenant_language", ""))
            if reason != RejectionReason.UNKNOWN_WORK_ORDER
            else ""
        )
        await self._send_message(
            OutboundMessage(
                rejected.work_order_id,
                rejected.role,
                render_rejection(RejectionReason(reason), language, rejected.limit),
            )
        )

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
        if work_order_id in self._completed_ids:
            return
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
                    if work_order_id in self._completed_ids:
                        continue
                    if isinstance(event, RejectedInbound):
                        await self._reject(event)
                        continue
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
        if work_order_id in self._completed_ids:
            return
        outbound = state.get("outbound_message")
        terminal = state.get("terminal_frame")
        if outbound is not None and leaks_internal_identifier(outbound.body):
            self._runtime_writer.write(
                event_type="outbound_identifier_blocked",
                work_order_id=work_order_id,
                detail={"role": outbound.role},
            )
            language = "es" if outbound.role == "handyman" else state.get("tenant_language", "en")
            outbound = replace(
                outbound, body=render_slot_fallback_reply(language, AmbiguityReason.OTHER)
            )
            state = {**state, "outbound_message": outbound}
        if outbound is not None:
            await self._send_message(outbound)
        for extra in state.get("extra_outbound") or ():
            await self._send_message(extra)
        if terminal is not None:
            await self._writer.write_terminal(terminal)
            self._completed_ids.add(work_order_id)
            self._trace_writer.write(
                event_type="terminal_result",
                work_order_id=work_order_id,
                detail={"result": terminal.result, "detail": terminal.detail},
            )
        saved = dict(state)
        if outbound is not None and not state.get("guard_blocked"):
            saved["last_outbound"] = {
                **(state.get("last_outbound") or {}),
                outbound.role: outbound.body,
            }
        if not state.get("guard_blocked"):
            saved["history"] = _extend_history(state)
        saved["guard_blocked"] = False
        saved["outbound_message"] = None
        saved["extra_outbound"] = ()
        saved["terminal_frame"] = None
        saved["inbound_message"] = None
        saved["resume_finalization"] = False
        saved["displaced_hold_event"] = False
        saved["displaced_work_orders"] = ()
        self._states[work_order_id] = saved

    async def _send_message(self, message: OutboundMessage) -> None:
        """Record the actual protocol message after its complete block is flushed."""
        await self._writer.write(message)
        self._trace_writer.write(
            event_type="outgoing_message",
            work_order_id=message.work_order_id,
            detail={"direction": "out", "role": message.role, "body": message.body},
        )

    async def _continue_finalization(self, work_order_id: str) -> None:
        while True:
            state = self._states.get(work_order_id)
            if state is None or not state.get("finalization_pending"):
                return
            result = await self._startup_graph.ainvoke({**state, "resume_finalization": True})
            await self._deliver_state(work_order_id, result, previous=state)
            if result.get("terminal_frame") is not None or not result.get("outbound_message"):
                return


_HISTORY_LIMIT = 8
_HISTORY_TEXT_LIMIT = 500


def _extend_history(state: dict[str, Any]) -> tuple[tuple[str, str, str], ...]:
    """Append the guard-cleared inbound text and our reply; blocked turns never get here."""
    history = tuple(state.get("history") or ())
    inbound = state.get("inbound_message")
    if inbound is not None and inbound.body.strip() and inbound.body != "<NO RESPONSE>":
        history += (("participant", inbound.role, inbound.body[:_HISTORY_TEXT_LIMIT]),)
    outbound = state.get("outbound_message")
    if outbound is not None:
        history += (("assistant", outbound.role, outbound.body[:_HISTORY_TEXT_LIMIT]),)
    return history[-_HISTORY_LIMIT:]
