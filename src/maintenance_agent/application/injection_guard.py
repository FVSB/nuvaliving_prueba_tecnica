"""Prompt-injection screening applied to every inbound participant message.

The LLM only supplies evidence (a probability and a suspicious fragment). The thresholds, the
fragment removal and every decision are deterministic code (constitution III).
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class GuardAction(StrEnum):
    PASS = "pass"
    PASS_CLEANED = "pass_cleaned"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class InjectionAssessment:
    """The classifier's answer to "is this text a prompt injection?"."""

    answer_yes: bool
    probability_yes: float


@dataclass(frozen=True, slots=True)
class GuardStage:
    """One classifier call, kept so the trace shows how the verdict was reached."""

    stage: str
    probability_yes: float
    answer_yes: bool


@dataclass(frozen=True, slots=True)
class GuardDecision:
    action: GuardAction
    body: str
    fragment: str | None = None
    reason: str = ""
    stages: tuple[GuardStage, ...] = ()


class InjectionClassifier(Protocol):
    async def assess(self, text: str) -> InjectionAssessment: ...

    async def extract_fragment(self, text: str) -> str: ...


def remove_fragment(body: str, fragment: str) -> str | None:
    """Remove the first occurrence of ``fragment`` from ``body``; None when it is not there."""
    needle = fragment.strip()
    if not needle:
        return None
    index = body.find(needle)
    if index < 0:
        index = body.casefold().find(needle.casefold())
    if index < 0:
        return None
    remainder = body[:index] + " " + body[index + len(needle) :]
    return " ".join(remainder.split())


class InjectionGuard:
    """Screen a message in up to three classifier passes; see the decision tree below.

    1. Whole message: probability <= threshold -> PASS.
    2. Extract the suspicious fragment and assess it alone: probability <= threshold -> PASS
       (false alarm, the original message continues).
    3. Remove the fragment with a deterministic tool and assess what remains: clean and not
       empty -> PASS_CLEANED (only the remainder continues); otherwise BLOCK.
    """

    def __init__(self, classifier: InjectionClassifier, threshold: float) -> None:
        if not 0.0 <= threshold < 1.0:
            raise ValueError("The injection threshold must satisfy 0 <= threshold < 1.")
        self._classifier = classifier
        self._threshold = threshold

    def _suspicious(self, assessment: InjectionAssessment) -> bool:
        return assessment.probability_yes > self._threshold

    async def screen(self, body: str) -> GuardDecision:
        stages: list[GuardStage] = []

        async def assess(stage: str, text: str) -> bool:
            assessment = await self._classifier.assess(text)
            stages.append(GuardStage(stage, assessment.probability_yes, assessment.answer_yes))
            return self._suspicious(assessment)

        if not await assess("message", body):
            return GuardDecision(GuardAction.PASS, body, stages=tuple(stages))
        fragment = (await self._classifier.extract_fragment(body)).strip()
        if not fragment or not await assess("fragment", fragment):
            return GuardDecision(
                GuardAction.PASS,
                body,
                fragment or None,
                "fragment_not_confirmed",
                tuple(stages),
            )
        remainder = remove_fragment(body, fragment)
        if remainder is None:
            return GuardDecision(
                GuardAction.BLOCK, body, fragment, "fragment_not_in_message", tuple(stages)
            )
        if not remainder:
            return GuardDecision(
                GuardAction.BLOCK, body, fragment, "nothing_left_after_removal", tuple(stages)
            )
        if await assess("remainder", remainder):
            return GuardDecision(
                GuardAction.BLOCK, body, fragment, "remainder_still_suspicious", tuple(stages)
            )
        return GuardDecision(
            GuardAction.PASS_CLEANED, remainder, fragment, "fragment_removed", tuple(stages)
        )


_NOTICES = {
    "es": "Su mensaje incumple las reglas de seguridad y no se ha procesado.",
    "en": "Your message violates the security rules and was not processed.",
    "fr": "Votre message enfreint les règles de sécurité et n'a pas été traité.",
    "de": "Ihre Nachricht verstößt gegen die Sicherheitsregeln und wurde nicht verarbeitet.",
    "it": "Il suo messaggio viola le regole di sicurezza e non è stato elaborato.",
    "pt": "A sua mensagem viola as regras de segurança e não foi processada.",
}


def render_security_notice(language: str) -> str:
    """Fixed, localized refusal text; unknown languages get the English/Spanish pair."""
    if language in _NOTICES:
        return _NOTICES[language]
    return f"{_NOTICES['en']} / {_NOTICES['es']}"
