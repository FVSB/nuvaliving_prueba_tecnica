"""Conservative deterministic interpretation of explicit yes/no replies."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import time

from maintenance_agent.domain.negotiation import DecisionValue

_YES = frozenset(
    {
        "si",
        "si puedo",
        "puedo",
        "yes i can",
        "i can",
        "yes",
        "y",
        "ok",
        "okay",
        "vale",
        "acepto",
        "confirmo",
        "confirmado",
        "confirmada",
        "correcto",
        "correcta",
        "de acuerdo",
        "estoy de acuerdo",
        "perfecto",
        "si por favor",
        "yes please",
        "sure",
    }
)
_NO = frozenset(
    {
        "no",
        "no gracias",
        "rechazo",
        "no acepto",
        "no puedo",
        "prefiero otro horario",
        "quiero otro horario",
        "no me viene bien",
        "ese horario no me viene bien",
        "no puedo ese dia",
        "not available",
        "that does not work",
    }
)


def interpret_explicit_decision(text: str) -> DecisionValue | None:
    """Return a decision only for a short, unambiguous explicit reply."""
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    phrase = " ".join(normalized.split())
    if phrase in _YES:
        return DecisionValue.YES
    if phrase in _NO:
        return DecisionValue.NO
    return None


_CANCEL_WORDS = frozenset(
    {"cancel", "cancelo", "cancela", "cancelar", "cancelado", "cancelamos", "cancelen"}
)
_CANCEL_PHRASES = (
    "ya no me sirve",
    "ya no me interesa",
    "ya no lo necesito",
    "no longer need",
    "no longer works",
    "never mind",
    "forget it",
)
_NEGATIONS = frozenset({"no", "not", "dont", "t", "nunca", "never", "tampoco"})
_MAX_CANCEL_WORDS = 14


def _fold(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in folded if not unicodedata.combining(char))


def interpret_cancellation(text: str) -> bool:
    """Return True only for a short, explicit request to cancel the pending proposal."""
    tokens = re.findall(r"\w+|[,.;:!?]", _fold(text), flags=re.UNICODE)
    words = [token for token in tokens if token[0].isalnum() or token[0] == "_"]
    if not words or len(words) > _MAX_CANCEL_WORDS:
        return False
    if "?" in tokens:
        return False
    phrase = " ".join(words)
    if any(item in phrase for item in _CANCEL_PHRASES):
        return True
    for index, token in enumerate(tokens):
        if token in _CANCEL_WORDS:
            return not (index > 0 and tokens[index - 1] in _NEGATIONS)
    return False


@dataclass(frozen=True, slots=True)
class AffirmedSlotMention:
    """An affirmative reply that names a time range and, optionally, a calendar date."""

    start: time
    end: time
    year: int | None = None
    month: int | None = None
    day: int | None = None


_AFFIRMATION = re.compile(
    r"^\W*(si|yes|ok|okay|vale|perfecto|claro|de acuerdo|sure|me viene bien)\b"
)
_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("enero", "january"),
            ("febrero", "february"),
            ("marzo", "march"),
            ("abril", "april"),
            ("mayo", "may"),
            ("junio", "june"),
            ("julio", "july"),
            ("agosto", "august"),
            ("septiembre", "september"),
            ("octubre", "october"),
            ("noviembre", "november"),
            ("diciembre", "december"),
        ),
        start=1,
    )
    for name in names
}
_MONTH_PATTERN = "|".join(_MONTHS)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH = re.compile(
    rf"\b(\d{{1,2}})\s+(?:de\s+)?({_MONTH_PATTERN})(?:\s+(?:de\s+)?(\d{{4}}))?\b"
)
_MONTH_DAY = re.compile(rf"\b({_MONTH_PATTERN})\s+(\d{{1,2}})(?:\s*,?\s*(\d{{4}}))?\b")
_TIME_RANGE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(?:a|to|hasta|-|–)\s*(?:las\s+)?(\d{1,2})(?::(\d{2}))?\b"
)


def parse_affirmed_slot(text: str) -> AffirmedSlotMention | None:
    """Parse "yes, <date?> from HH:MM to HH:MM"; None unless affirmative with a time range."""
    folded = " ".join(_fold(text).split())
    if not _AFFIRMATION.match(folded):
        return None
    year = month = day = None
    remainder = folded
    if match := _ISO_DATE.search(remainder):
        year, month, day = (int(group) for group in match.groups())
    elif match := _DAY_MONTH.search(remainder):
        day, month = int(match.group(1)), _MONTHS[match.group(2)]
        year = int(match.group(3)) if match.group(3) else None
    elif match := _MONTH_DAY.search(remainder):
        month, day = _MONTHS[match.group(1)], int(match.group(2))
        year = int(match.group(3)) if match.group(3) else None
    if match:
        remainder = remainder[: match.start()] + " " + remainder[match.end() :]
    found = _TIME_RANGE.search(remainder)
    if found is None:
        return None
    start_hour, start_minute, end_hour, end_minute = found.groups()
    try:
        return AffirmedSlotMention(
            time(int(start_hour), int(start_minute or 0)),
            time(int(end_hour), int(end_minute or 0)),
            year,
            month,
            day,
        )
    except ValueError:
        return None
