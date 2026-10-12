"""Asynchronous stdin/stdout adapter for the binding terminal protocol."""

import asyncio
import re
import sys
from collections.abc import AsyncIterator
from io import TextIOBase

from maintenance_agent.application.messages import InboundMessage, OutboundMessage

# The body is deliberately captured as the complete remainder so embedded pipes survive intact.
INBOUND_MESSAGE_PATTERN = re.compile(
    r"^(?P<work_order_id>[^|\s]+)\|(?P<role>tenant|handyman) (?P<body>.*)$"
)


class InputFormatError(ValueError):
    """Raised when a line cannot be represented as a valid inbound message."""


def parse_inbound_message(line: str) -> InboundMessage:
    """Parse one valid protocol line without altering its body."""
    match = INBOUND_MESSAGE_PATTERN.fullmatch(line)
    if match is None:
        raise InputFormatError("Inbound message does not match the documented protocol.")
    return InboundMessage(**match.groupdict())


class AsyncStdinReader:
    """Read terminal lines without blocking the event loop."""

    def __init__(self, stream: TextIOBase | None = None) -> None:
        self._stream = stream or sys.stdin

    async def messages(self) -> AsyncIterator[InboundMessage]:
        while True:
            line = await asyncio.to_thread(self._stream.readline)
            # Let the worker mark itself idle before asyncio.run() shuts down its executor.
            await asyncio.sleep(0)
            if not line:
                return
            yield parse_inbound_message(line.rstrip("\r\n"))


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
