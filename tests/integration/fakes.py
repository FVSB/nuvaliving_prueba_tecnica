"""Test-only collaborators for deterministic asynchronous integration tests."""

from collections.abc import AsyncIterator, Iterable
from datetime import datetime

from maintenance_agent.application.conversation import AvailabilityInterpretation
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


# Prose that the deterministic slot-prose check always rejects (it promises availability).
BAD_PROSE = ("Garantizamos la visita.", "Elija una.")


class FakeConversationHandler:
    """Scripted structured provider for deterministic conversation and CLI tests."""

    def __init__(
        self,
        availability=None,
        availability_results=None,
        slot_prose=None,
        detected_languages=None,
    ) -> None:
        self.slot_prose: list[tuple[str, str]] = list(slot_prose or [])
        self.detected_languages: list[str] = list(detected_languages or [])
        self.slot_compose_calls: list[tuple[str, dict[str, str]]] = []
        self.detect_calls: list[str] = []
        self.translate_calls: list[tuple[str, str]] = []
        self._slot_language = ""
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
        self._slot_language = language.lower()
        if self.slot_prose:
            return self.slot_prose.pop(0)
        return f"{language}: intro", f"{language}: ask"

    async def detect_language(self, text: str) -> str:
        self.detect_calls.append(text)
        if self.detected_languages:
            return self.detected_languages.pop(0)
        return self._slot_language

    async def translate(self, text: str, language: str) -> str:
        self.translate_calls.append((text, language))
        return text
