from datetime import time

import pytest

from maintenance_agent.domain.decisions import (
    AffirmedSlotMention,
    interpret_cancellation,
    interpret_explicit_decision,
    interpret_single_offer_reply,
    parse_affirmed_slot,
)
from maintenance_agent.domain.negotiation import DecisionValue


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


@pytest.mark.parametrize(
    "text",
    ["ok me gusta", "Acepto, me parece bien", "sí, me viene bien", "vale perfecto", "sounds good"],
)
def test_single_offer_reply_accepts_natural_acceptance(text: str) -> None:
    assert interpret_single_offer_reply(text) is DecisionValue.YES


@pytest.mark.parametrize(
    "text",
    [
        "si pero no",
        "ok pero a las 5",
        "no me gusta",
        "ok el 15 a las 10",
        "me gusta otro horario",
        "ok si puedo",
        "hola",
        "ok, me parece bien esa hora para la visita de mañana por favor gracias",
    ],
)
def test_single_offer_reply_never_accepts_conditions_changes_or_refusals(text: str) -> None:
    assert interpret_single_offer_reply(text) is not DecisionValue.YES


def test_strict_decision_still_rejects_natural_acceptance() -> None:
    assert interpret_explicit_decision("ok me gusta") is None


@pytest.mark.parametrize(
    "text",
    ["sí", "si", "Sí.", "SI", "sí, es correcto", "si es correcto", "Yes", "yes please",
     "sí por favor", "Yes, I accept", "I confirm", "yep", "Correct", "ok, gracias", "Sure thing"],
)  # fmt: skip
def test_explicit_yes_variants_with_and_without_accents(text: str) -> None:
    assert interpret_explicit_decision(text) is DecisionValue.YES


@pytest.mark.parametrize(
    "text",
    ["no", "No.", "NO", "no, gracias", "nope", "Nah", "I reject", "I decline", "no es correcto",
     "incorrecto", "Not correct"],
)  # fmt: skip
def test_explicit_no_variants_with_and_without_accents(text: str) -> None:
    assert interpret_explicit_decision(text) is DecisionValue.NO


@pytest.mark.parametrize(
    "text",
    ["sí, acepto la visita del miércoles 14 de 10:00 a 12:00", "tal vez", "mmm", "", "2026-10-14",
     "sí pero no", "ok pero a las 5", "wait, no, maybe"],
)  # fmt: skip
def test_anything_else_is_not_an_explicit_decision(text: str) -> None:
    assert interpret_explicit_decision(text) is None


@pytest.mark.parametrize(
    "text",
    ["no", "no, I cannot do the 15th", "No, mejor otra hora", "no me viene bien el 15 a las 10"],
)
def test_single_offer_reply_reads_a_leading_no_as_a_refusal(text: str) -> None:
    assert interpret_single_offer_reply(text) is DecisionValue.NO


@pytest.mark.parametrize("text", ["no sé", "no estoy seguro", "not sure, maybe", "no lo sé"])
def test_single_offer_reply_leaves_unsure_nos_unresolved(text: str) -> None:
    assert interpret_single_offer_reply(text) is None
