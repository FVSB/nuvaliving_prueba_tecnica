"""Test-only collaborators for deterministic asynchronous integration tests."""

from collections.abc import AsyncIterator, Iterable
from datetime import datetime

from maintenance_agent.application.conversation import (
    AvailabilityInterpretation,
    ValidationVerdict,
)
from maintenance_agent.application.messages import InboundMessage
from maintenance_agent.domain.negotiation import ParticipantRole, TimeInterval
from maintenance_agent.infrastructure.cli_transport import parse_inbound_message


class FakeStdinReader:
    """Yield fixed valid protocol lines without touching process stdin or threads."""

    def __init__(self, lines: Iterable[str]) -> None:
        self._lines = tuple(lines)

    async def messages(self) -> AsyncIterator[InboundMessage]:
        for line in self._lines:
            yield parse_inbound_message(line)


class FakeConversationHandler:
    """Scripted structured provider for deterministic conversation and CLI tests."""

    def __init__(self, availability=None, availability_results=None, slot_verdicts=None) -> None:
        self.slot_verdicts: list[ValidationVerdict] = list(slot_verdicts or [])
        self.slot_compose_calls: list[tuple[str, dict[str, str]]] = []
        self.slot_validate_calls: list[tuple[str, dict[str, str]]] = []
        self.availability = {
            ParticipantRole(key): tuple(value) for key, value in (availability or {}).items()
        }
        self.availability_results = {
            ParticipantRole(key): list(value) for key, value in (availability_results or {}).items()
        }
        self.compositions: list[tuple[str, str, dict[str, str]]] = []
        self.availability_calls: list[tuple[str, ParticipantRole, datetime, str]] = []
        self.history_calls: list[tuple[tuple[str, str], ...]] = []

    async def interpret_availability(
        self,
        text: str,
        role: ParticipantRole,
        reference_time: datetime,
        timezone_name: str,
        history: tuple[tuple[str, str], ...] = (),
    ) -> AvailabilityInterpretation:
        self.availability_calls.append((text, role, reference_time, timezone_name))
        self.history_calls.append(history)
        scripted = self.availability_results.get(role, [])
        if scripted:
            return scripted.pop(0)
        value = self.availability.get(role, ())
        if value and isinstance(value[0], TimeInterval):
            intervals = value
        else:
            intervals = tuple(
                TimeInterval(datetime.fromisoformat(start), datetime.fromisoformat(end))
                for start, end in value
            )
        return AvailabilityInterpretation(intervals, True, False)

    async def compose(self, intent: str, language: str, facts: dict[str, str]) -> str:
        self.compositions.append((intent, language, dict(facts)))
        return f"{language}: {intent} {facts}"

    async def compose_slot_reply(self, language: str, facts: dict[str, str]) -> tuple[str, str]:
        self.slot_compose_calls.append((language, dict(facts)))
        return f"{language}: intro", f"{language}: ask"

    async def validate_slot_reply(self, reply: str, facts: dict[str, str]) -> ValidationVerdict:
        self.slot_validate_calls.append((reply, dict(facts)))
        if self.slot_verdicts:
            return self.slot_verdicts.pop(0)
        return ValidationVerdict(True, None)
