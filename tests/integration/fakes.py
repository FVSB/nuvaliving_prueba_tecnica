"""Test-only collaborators for deterministic asynchronous integration tests."""

from collections.abc import AsyncIterator, Iterable

from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.infrastructure.cli_transport import parse_inbound_message


class FakeStdinReader:
    """Yield fixed valid protocol lines without touching process stdin or threads."""

    def __init__(self, lines: Iterable[str]) -> None:
        self._lines = tuple(lines)

    async def messages(self) -> AsyncIterator[InboundMessage]:
        for line in self._lines:
            yield parse_inbound_message(line)
