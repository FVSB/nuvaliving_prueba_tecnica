"""Conservative deterministic interpretation of explicit yes/no replies."""

import re
import unicodedata

from maintenance_agent.domain.negotiation import DecisionValue

_YES = frozenset(
    {
        "si",
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
