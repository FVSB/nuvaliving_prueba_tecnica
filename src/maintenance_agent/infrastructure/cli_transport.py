"""Asynchronous stdin/stdout adapter for the binding terminal protocol."""

import asyncio
import re
import sys
from collections.abc import AsyncIterator
from io import TextIOBase

from maintenance_agent.application.messages import (
    InboundMessage,
    OutboundMessage,
    RejectedInbound,
    TerminalFrame,
)
from maintenance_agent.application.rejections import RejectionReason, preview
from maintenance_agent.infrastructure.trace_writer import TraceWriter

# The body is deliberately captured as the complete remainder so embedded pipes survive intact.
INBOUND_MESSAGE_PATTERN = re.compile(
    r"^(?P<work_order_id>[^|\s]+)\|(?P<role>tenant|handyman) (?P<body>.*)$"
)
# Same shape as above but tolerating a missing separator, so an empty body can be answered.
ADDRESSABLE_LINE_PATTERN = re.compile(
    r"^(?P<work_order_id>[^|\s]+)\|(?P<role>tenant|handyman)(?: (?P<body>.*))?$"
)


class InputFormatError(ValueError):
    """Raised when a line cannot be represented as a valid inbound message."""


def parse_inbound_message(line: str) -> InboundMessage:
    """Parse one valid protocol line without altering its body."""
    match = INBOUND_MESSAGE_PATTERN.fullmatch(line)
    if match is None:
        raise InputFormatError("Inbound message does not match the documented protocol.")
    return InboundMessage(**match.groupdict())


def validate_inbound_line(line: str, max_message_length: int) -> InboundMessage | RejectedInbound:
    """Classify a line; raise InputFormatError when no sender can be identified."""
    match = ADDRESSABLE_LINE_PATTERN.fullmatch(line)
    if match is None:
        raise InputFormatError("Inbound message does not match the documented protocol.")
    work_order_id, role = match["work_order_id"], match["role"]
    body = match["body"] or ""
    reason: RejectionReason | None = None
    if not body.strip():
        reason = RejectionReason.EMPTY_BODY
    elif len(body) > max_message_length:
        reason = RejectionReason.TOO_LONG
    if reason is None:
        return InboundMessage(work_order_id, role, body)
    return RejectedInbound(
        work_order_id, role, reason, len(body), preview(body), max_message_length
    )


class AsyncStdinReader:
    """Read terminal lines without blocking the event loop."""

    def __init__(
        self,
        stream: TextIOBase | None = None,
        runtime_writer: TraceWriter | None = None,
        *,
        max_message_length: int,
    ) -> None:
        self._stream = stream or sys.stdin
        self._runtime_writer = runtime_writer
        self._max_message_length = max_message_length

    async def messages(self) -> AsyncIterator[InboundMessage | RejectedInbound]:
        while True:
            line = await asyncio.to_thread(self._stream.readline)
            # Let the worker mark itself idle before asyncio.run() shuts down its executor.
            await asyncio.sleep(0)
            if not line:
                return
            message_line = line.rstrip("\r\n")
            try:
                message = validate_inbound_line(message_line, self._max_message_length)
            except InputFormatError:
                # No sender can be identified, so nobody can be answered: trace only.
                if self._runtime_writer is not None:
                    self._runtime_writer.write(
                        event_type="malformed_input",
                        detail={
                            "reason": "protocol_mismatch",
                            "line_length": len(message_line),
                            "input_line": message_line,
                        },
                    )
                    self._runtime_writer.write(
                        event_type="message_rejected",
                        detail={
                            "reason": RejectionReason.PROTOCOL_MISMATCH,
                            "length": len(message_line),
                            "input_preview": preview(message_line),
                        },
                    )
                continue
            yield message


class AsyncStdoutWriter:
    """Serialize whole protocol blocks and flush each completed block."""

    def __init__(self, stream: TextIOBase | None = None) -> None:
        self._stream = stream or sys.stdout
        self._lock = asyncio.Lock()

    async def write(self, message: OutboundMessage) -> None:
        block = f"WOID:{message.work_order_id}|ROLE:{message.role}\n{message.body}\n\n"
        async with self._lock:
            self._stream.write(block)
            self._stream.flush()

    async def write_terminal(self, frame: TerminalFrame) -> None:
        """Write and flush the exact two-line terminal outcome without message framing."""
        block = f"WOID:{frame.work_order_id}|RESULT:{frame.result}\n{frame.detail}\n"
        async with self._lock:
            self._stream.write(block)
            self._stream.flush()
