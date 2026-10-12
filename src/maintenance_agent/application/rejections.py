"""Fixed, localized replies for inbound lines rejected before reaching any work order."""

from enum import StrEnum

PREVIEW_LENGTH = 200


class RejectionReason(StrEnum):
    EMPTY_BODY = "empty_body"
    TOO_LONG = "too_long"
    UNKNOWN_WORK_ORDER = "unknown_work_order"
    PROTOCOL_MISMATCH = "protocol_mismatch"


_NOTICES = {
    RejectionReason.EMPTY_BODY: {
        "es": "Su mensaje está vacío y no se ha procesado. Envíe un mensaje con contenido.",
        "en": "Your message is empty and was not processed. Please send a message with content.",
    },
    RejectionReason.TOO_LONG: {
        "es": "Su mensaje supera el máximo de {limit} caracteres y no se ha procesado.",
        "en": "Your message exceeds the maximum of {limit} characters and was not processed.",
    },
    RejectionReason.UNKNOWN_WORK_ORDER: {
        "es": "La orden de trabajo indicada no existe y el mensaje no se ha procesado.",
        "en": "The indicated work order does not exist and the message was not processed.",
    },
}


def render_rejection(reason: RejectionReason, language: str, limit: int) -> str:
    """Fixed reply for ``reason``; unknown languages get the English/Spanish pair."""
    notices = _NOTICES[reason]
    if language in notices:
        return notices[language].format(limit=limit)
    return f"{notices['en']} / {notices['es']}".format(limit=limit)


def preview(text: str) -> str:
    """Truncate submitted text for trace events."""
    return text[:PREVIEW_LENGTH]
