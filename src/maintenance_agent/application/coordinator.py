"""Per-work-order queues, retained graph state and concurrent independent orders."""

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from maintenance_agent.application.conversation import AmbiguityReason
from maintenance_agent.application.messages import (
    InboundMessage,
    OutboundMessage,
    RejectedInbound,
    TerminalFrame,
)
from maintenance_agent.application.outbound_guard import leaks_internal_identifier
from maintenance_agent.application.rejections import (
    RejectionReason,
    preview,
    render_rejection,
)
from maintenance_agent.application.retry_queue import NoResponseRetryQueue, RetryEntry
from maintenance_agent.application.slot_table import render_slot_fallback_reply
from maintenance_agent.domain.work_orders import WorkOrder
from maintenance_agent.infrastructure.cli_transport import AsyncStdoutWriter
from maintenance_agent.infrastructure.trace_writer import TraceWriter

InboundNode = Callable[[InboundMessage], Awaitable[OutboundMessage]]


@dataclass(frozen=True, slots=True)
class DisplacedHoldEvent:
    work_order_id: str


@dataclass(frozen=True, slots=True)
class RetryDueEvent:
    """A silent participant's wait expired: send a reminder or, if exhausted, close the order."""

    entry: RetryEntry
    exhausted: bool
    at_eof: bool = False


CoordinatorEvent = InboundMessage | RejectedInbound | DisplacedHoldEvent | RetryDueEvent


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
        max_message_length: int,
        retry_queue: NoResponseRetryQueue,
        retry_poll_seconds: float,
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
        self._retry_queue = retry_queue
        self._silenced: dict[str, str] = {}
        self._retry_poll_seconds = retry_poll_seconds

    async def run(self, work_orders: Sequence[WorkOrder]) -> None:
        status = "completed"
        poller: asyncio.Task[None] | None = None
        self._known_ids = frozenset(order.work_order_id for order in work_orders)
        try:
            self._trace_writer.write(
                event_type="work_orders_starting", detail={"count": len(work_orders)}
            )
            await asyncio.gather(*(self._start(work_order) for work_order in work_orders))
            self._trace_writer.write(
                event_type="work_orders_started", detail={"count": len(work_orders)}
            )
            poller = asyncio.create_task(self._poll_retries())
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
            poller.cancel()
            while self._all_workers:  # let queued messages register their retry first
                await asyncio.gather(*self._all_workers)
            self._drain_retries_at_eof()
            while self._all_workers:
                await asyncio.gather(*self._all_workers)
            self._trace_writer.write(event_type="run_completed", detail={})
        except Exception as error:
            status = "failed"
            if poller is not None:
                poller.cancel()
            self._runtime_writer.write(
                event_type="run_error", detail={"error_type": type(error).__name__}
            )
            raise
        finally:
            self._manifest_writer.write(event_type="run_finished", detail={"status": status})

    async def _poll_retries(self) -> None:
        """Every few seconds, hand the orders whose wait expired to their own worker."""
        while True:
            await asyncio.sleep(self._retry_poll_seconds)
            for entry in self._retry_queue.pop_due():
                exhausted = self._retry_queue.exhausted(entry)
                self._enqueue(entry.work_order_id, RetryDueEvent(entry, exhausted))

    def _drain_retries_at_eof(self) -> None:
        """No human can answer once input ended: close the retrying orders without waiting."""
        for entry in self._retry_queue.drain():
            self._trace_writer.write(
                event_type="no_response_retries_cut_at_eof",
                work_order_id=entry.work_order_id,
                detail={"role": entry.role, "retries_sent": entry.attempt},
            )
            self._enqueue(entry.work_order_id, RetryDueEvent(entry, exhausted=True, at_eof=True))

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
        order_id = message.work_order_id
        if order_id in self._completed_ids:
            self._trace_writer.write(
                event_type="message_ignored_after_terminal",
                work_order_id=order_id,
                detail={"role": message.role, "is_no_response": message.body == "<NO RESPONSE>"},
            )
            return
        if message.body == "<NO RESPONSE>":
            if order_id in self._silenced:
                self._trace_writer.write(
                    event_type="no_response_ignored_already_retrying",
                    work_order_id=order_id,
                    detail={"role": message.role},
                )
                return
            question = (self._states.get(order_id) or {}).get("pending_question")
            self._silenced[order_id] = question.role.value if question else message.role
        elif self._silenced.get(order_id) == message.role:
            del self._silenced[order_id]
            self._retry_queue.cancel(order_id)
            self._trace_writer.write(
                event_type="no_response_retry_cancelled",
                work_order_id=order_id,
                detail={"role": message.role, "reason": "participant answered"},
            )
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
                    if isinstance(event, RetryDueEvent):
                        if (
                            current is None
                            or "graph_cursor" not in current
                            or work_order_id not in self._silenced  # answered meanwhile
                        ):
                            continue
                        graph_input = {
                            **current,
                            "resume_finalization": False,
                            "retry_event": {
                                "role": event.entry.role,
                                "attempt": event.entry.attempt,
                                "exhausted": event.exhausted,
                                "at_eof": event.at_eof,
                            },
                        }
                        result = await self._startup_graph.ainvoke(graph_input)
                        if not event.exhausted:
                            self._retry_queue.schedule(
                                work_order_id, event.entry.role, event.entry.attempt + 1
                            )
                    elif current is not None and "graph_cursor" in current:
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
                    retry_role = result.get("retry_request")
                    if retry_role and work_order_id not in self._completed_ids:
                        self._retry_queue.schedule(work_order_id, retry_role)
                        self._trace_writer.write(
                            event_type="no_response_retry_scheduled",
                            work_order_id=work_order_id,
                            detail={
                                "role": retry_role,
                                "max_retries": self._retry_queue.max_retries,
                            },
                        )
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
                    await self._fail_to_review(work_order_id, error)
                    continue
                finally:
                    queue.task_done()
        finally:
            self._trace_writer.write(
                event_type="order_worker_finished", work_order_id=work_order_id, detail={}
            )
            self._workers.pop(work_order_id, None)

    async def _fail_to_review(self, work_order_id: str, error: Exception) -> None:
        """Close a failed order with the protocol alert instead of killing the worker."""
        if work_order_id in self._completed_ids:
            return
        frame = TerminalFrame(work_order_id, "requires_review", f"ERROR:{type(error).__name__}")
        await self._writer.write_terminal(frame)
        self._completed_ids.add(work_order_id)
        self._retry_queue.cancel(work_order_id)
        self._trace_writer.write(
            event_type="terminal_result",
            work_order_id=work_order_id,
            detail={"result": frame.result, "detail": frame.detail},
        )

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
            self._retry_queue.cancel(work_order_id)
            self._silenced.pop(work_order_id, None)
            self._trace_writer.write(
                event_type="terminal_result",
                work_order_id=work_order_id,
                detail={"result": terminal.result, "detail": terminal.detail},
            )
        saved = dict(state)
        # A reminder must not replace the original message it re-sends.
        is_reminder = bool(state.get("retry_event"))
        if outbound is not None and not state.get("guard_blocked") and not is_reminder:
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
        saved["retry_request"] = None
        saved["retry_event"] = None
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
_TABLE_ROW = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|.*?(\d{2}:\d{2})\D+(\d{2}:\d{2})\s*\|\s*$")


def _compact_tables(body: str) -> str:
    """Replace each slot table by one summary line so the model sees what was shown."""
    lines: list[str] = []
    rows: list[tuple[str, str, str]] = []
    for line in body.splitlines():
        if line.startswith("|"):
            match = _TABLE_ROW.match(line)
            if match:
                rows.append((match[1], match[2], match[3]))
            continue  # table header, separator and rows are replaced by the summary
        if rows:
            lines.append(_table_summary(rows))
            rows = []
        lines.append(line)
    if rows:
        lines.append(_table_summary(rows))
    return "\n".join(lines)


def _table_summary(rows: list[tuple[str, str, str]]) -> str:
    days = sorted({day for day, _, _ in rows})
    first = min(start for _, start, _ in rows)
    last = max(end for _, _, end in rows)
    span = days[0] if len(days) == 1 else f"{days[0]}..{days[-1]}"
    return f"[Slot table shown: {len(rows)} slots, dates {span}, times {first}-{last}]"


def _extend_history(state: dict[str, Any]) -> tuple[tuple[str, str, str], ...]:
    """Append the guard-cleared inbound text and our reply; blocked turns never get here."""
    history = tuple(state.get("history") or ())
    inbound = state.get("inbound_message")
    if inbound is not None and inbound.body.strip() and inbound.body != "<NO RESPONSE>":
        history += (("participant", inbound.role, inbound.body[:_HISTORY_TEXT_LIMIT]),)
    outbound = state.get("outbound_message")
    if outbound is not None:
        history += (
            ("assistant", outbound.role, _compact_tables(outbound.body)[:_HISTORY_TEXT_LIMIT]),
        )
    return history[-_HISTORY_LIMIT:]
