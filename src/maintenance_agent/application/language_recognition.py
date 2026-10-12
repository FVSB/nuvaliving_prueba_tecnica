"""Application port for language recognition."""

from typing import Protocol

from maintenance_agent.domain.languages import LanguageRecognitionResult


class LanguageRecognizer(Protocol):
    """Recognize a work-order description through an injected implementation."""

    async def recognize(self, description: str) -> LanguageRecognitionResult:
        """Return a validated language result for the supplied description."""


class StaticLanguageRecognizer:
    """Return a fixed result for tests and credential-free local startup."""

    def __init__(self, result: LanguageRecognitionResult) -> None:
        self._result = result

    async def recognize(self, description: str) -> LanguageRecognitionResult:
        """Return the configured result without inspecting the description."""
        return self._result
