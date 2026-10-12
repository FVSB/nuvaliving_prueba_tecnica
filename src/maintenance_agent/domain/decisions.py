"""Conservative deterministic interpretation of explicit yes/no replies."""

import re
from dataclasses import dataclass
from datetime import time

from maintenance_agent.domain.negotiation import DecisionValue
from maintenance_agent.domain.text import fold

# Spanish and English variants. `fold` strips accents, so "sí" and "si" are one entry.
_YES = frozenset(
    {
        "si",
        "si puedo",
        "puedo",
        "yes i can",
        "i can",
        "yes",
        "yep",
        "yeah",
        "y",
        "ok",
        "okay",
        "vale",
        "claro",
        "claro que si",
        "acepto",
        "si acepto",
        "i accept",
        "yes i accept",
        "accept",
        "confirmo",
        "si confirmo",
        "i confirm",
        "yes i confirm",
        "confirm",
        "confirmado",
        "confirmada",
        "correcto",
        "correcta",
        "es correcto",
        "es correcta",
        "si es correcto",
        "si es correcta",
        "yes correct",
        "correct",
        "yes it is correct",
        "yes its correct",
        "that is correct",
        "de acuerdo",
        "estoy de acuerdo",
        "perfecto",
        "si por favor",
        "yes please",
        "sure",
        "sure thing",
    }
)
_NO = frozenset(
    {
        "no",
        "n",
        "nope",
        "nah",
        "not",
        "no gracias",
        "no thanks",
        "rechazo",
        "rechazar",
        "reject",
        "i reject",
        "decline",
        "i decline",
        "no acepto",
        "i do not accept",
        "not accept",
        "no confirmo",
        "no es correcto",
        "no es correcta",
        "incorrecto",
        "incorrecta",
        "es incorrecto",
        "not correct",
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
# Courtesy words never change a yes or no, so they are dropped before the lookup.
_COURTESY = frozenset({"por", "favor", "please", "gracias", "muchas", "thanks", "thank", "you"})


def interpret_explicit_decision(text: str) -> DecisionValue | None:
    """Return a decision only for a short, unambiguous explicit reply.

    Accepts the Spanish and English variants above with or without accents, ignores
    punctuation and courtesy words. Anything else returns None so the caller asks again.
    """
    normalized = fold(text)
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    phrase = " ".join(word for word in normalized.split() if word not in _COURTESY)
    if phrase in _YES:
        return DecisionValue.YES
    if phrase in _NO:
        return DecisionValue.NO
    return None


# Natural acceptances ("ok me gusta", "me parece bien") that only bind a *single* offer.
_ACCEPT_CUES = frozenset(
    {
        "ok", "okay", "vale", "si", "yes", "yeah", "yep", "claro", "perfecto", "genial",
        "listo", "dale", "bien", "sure", "fine", "great", "agreed", "acepto", "confirmo",
        "adelante", "buenisimo", "excelente",
    }
)  # fmt: skip
_ACCEPT_PHRASES = (
    "me gusta",
    "me parece bien",
    "me viene bien",
    "me va bien",
    "me sirve",
    "me conviene",
    "de acuerdo",
    "esta bien",
    "sounds good",
    "works for me",
    "that works",
    "i accept",
    "i agree",
    "looks good",
)
# Any of these turns a short "ok ..." into a conditional, a change or a refusal.
_BLOCKERS = frozenset(
    {
        "no", "not", "pero", "but", "nunca", "never", "tampoco", "sin", "aunque", "excepto",
        "except", "otro", "otra", "otros", "otras", "other", "another", "different", "mejor",
        "prefiero", "cambiar", "change", "sino", "si", "if", "solo", "only", "siempre",
    }
)  # fmt: skip
_MAX_SINGLE_OFFER_WORDS = 8
_REFUSAL_OPENERS = frozenset({"no", "nope", "nah"})
_UNSURE = frozenset({"se", "seguro", "segura", "sure", "know", "idea", "talvez", "maybe", "quiza"})


def interpret_single_offer_reply(text: str) -> DecisionValue | None:
    """Like `interpret_explicit_decision`, but also accepts natural short acceptances.

    Only for questions about exactly one offered slot or proposal: with several options a loose
    "ok" does not say which one, so callers with several options must use the strict function.
    A leading "no" is a refusal even with a date; otherwise a negation, condition, change,
    question, digit (a date/time) or long reply stays None.
    """
    decision = interpret_explicit_decision(text)
    if decision is not None:
        return decision
    folded = fold(text)
    if "?" in folded:
        return None
    words = re.findall(r"[^\W\d_]+", folded, flags=re.UNICODE)
    # A refusal may restate the date ("no, I cannot do the 15th"); only a leading "no" counts.
    if words and words[0] in _REFUSAL_OPENERS and not _UNSURE.intersection(words):
        return DecisionValue.NO
    if any(char.isdigit() for char in folded):
        return None
    if not words or len(words) > _MAX_SINGLE_OFFER_WORDS:
        return None
    # "si" opens a plain "si, me gusta" but a later "si" is a condition ("... si puedo").
    if any(word in _BLOCKERS for word in words[1:]) or words[0] in (_BLOCKERS - {"si"}):
        return None
    phrase = " ".join(words)
    if words[0] in _ACCEPT_CUES or any(item in phrase for item in _ACCEPT_PHRASES):
        return DecisionValue.YES
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


def interpret_cancellation(text: str) -> bool:
    """Return True only for a short, explicit request to cancel the pending proposal."""
    tokens = re.findall(r"\w+|[,.;:!?]", fold(text), flags=re.UNICODE)
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
    r"^\W*(si|yes|ok|okay|vale|perfecto|claro|de acuerdo|sure|me viene bien|acepto|confirmo"
    r"|i accept|i agree|accept|agreed|me parece bien|me gusta)\b"
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
    folded = " ".join(fold(text).split())
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
