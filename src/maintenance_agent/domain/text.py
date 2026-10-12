"""Shared deterministic text normalisation for domain interpretation."""

import unicodedata


def fold(text: str) -> str:
    """Casefold and strip diacritics, so 'Sí' and 'si' compare equal."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in folded if not unicodedata.combining(char))
