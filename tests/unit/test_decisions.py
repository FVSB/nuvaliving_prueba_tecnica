from datetime import time

import pytest

from maintenance_agent.domain.decisions import (
    AffirmedSlotMention,
    interpret_cancellation,
    parse_affirmed_slot,
)


@pytest.mark.parametrize(
    "text",
    ["No, cancelo, ya no me sirve", "cancelar", "Cancel", "please cancel the visit"],
)
def test_cancellation_phrases(text: str) -> None:
    assert interpret_cancellation(text) is True


@pytest.mark.parametrize(
    "text",
    ["no", "yes", "no cancelo", "don't cancel", "Can I cancel later?", "", "2026-10-14 10-12"],
)
def test_not_cancellation(text: str) -> None:
    assert interpret_cancellation(text) is False


def test_affirmed_slot_with_spanish_date() -> None:
    assert parse_affirmed_slot("Sí, me viene bien el 13 de octubre de 2026 de 9:00 a 11:00") == (
        AffirmedSlotMention(time(9), time(11), 2026, 10, 13)
    )


def test_affirmed_slot_without_date_and_iso_date() -> None:
    assert parse_affirmed_slot("Sí, me viene bien el de 9:00 a 11:00") == AffirmedSlotMention(
        time(9), time(11)
    )
    assert parse_affirmed_slot("ok 2026-10-13 10-12") == AffirmedSlotMention(
        time(10), time(12), 2026, 10, 13
    )


def test_not_affirmed_without_affirmation_or_range() -> None:
    assert parse_affirmed_slot("El 13 de octubre de 9:00 a 11:00") is None
    assert parse_affirmed_slot("Sí") is None
    assert parse_affirmed_slot("Sí, el 13 de octubre") is None
