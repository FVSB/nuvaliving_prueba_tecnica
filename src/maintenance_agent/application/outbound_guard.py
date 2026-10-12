"""Deterministic last gate: internal identifiers never reach a participant."""

import re

# Slot labels (SLOT-...), counter-proposal ids, raw slot_id words and 16-hex stable ids.
_INTERNAL_ID = re.compile(
    r"SLOT-[0-9A-Za-z-]+|\bcounter:\S+|\bslot[_ -]?id\b|\b[0-9a-f]{16}\b",
    re.IGNORECASE,
)


def leaks_internal_identifier(text: str) -> bool:
    return _INTERNAL_ID.search(text) is not None
