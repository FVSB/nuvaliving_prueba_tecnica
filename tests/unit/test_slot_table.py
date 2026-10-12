from datetime import timezone

from maintenance_agent.application.conversation import AmbiguityReason, PartOfDay
from maintenance_agent.application.slot_table import (
    SlotGridSpec,
    SlotTable,
    check_slot_prose,
    compose_slot_reply_text,
    derive_open_slots,
    describe_window,
    filter_slots,
    render_slot_fallback_reply,
    reply_embeds_table,
)
from tests.unit.slot_helpers import NOW, appointment_at, snapshot_with

GRID = SlotGridSpec()


def test_grid_has_five_slots_per_day_for_seven_days() -> None:
    slots = derive_open_slots(snapshot_with(), NOW, "Europe/Madrid", GRID)
    assert len(slots) == 35
    assert slots[0].start_local == "09:00" and slots[-1].end_local == "19:00"


def test_occupied_slot_is_excluded() -> None:
    slots = derive_open_slots(snapshot_with(appointment_at(11)), NOW, "Europe/Madrid", GRID)
    assert len(slots) == 34
    assert all(slot.start_local != "11:00" or slot.local_date != "2026-10-12" for slot in slots)


def test_overlap_by_partial_slot_excludes_it() -> None:
    slots = derive_open_slots(snapshot_with(appointment_at(10)), NOW, "Europe/Madrid", GRID)
    day = [s.start_local for s in slots if s.local_date == "2026-10-12"]
    assert day == ["13:00", "15:00", "17:00"]


def test_render_is_byte_deterministic_and_ordered() -> None:
    first = SlotTable(derive_open_slots(snapshot_with(), NOW, "Europe/Madrid", GRID), "en")
    second = SlotTable(
        tuple(reversed(derive_open_slots(snapshot_with(), NOW, "Europe/Madrid", GRID))), "en"
    )
    assert first.render_markdown() == second.render_markdown()
    assert first.render_markdown().splitlines()[2].startswith("| 2026-10-12")
    assert "SLOT-" not in first.render_markdown()


def test_slot_id_uses_utc() -> None:
    slot = derive_open_slots(snapshot_with(), NOW, "Europe/Madrid", GRID)[0]
    assert slot.interval.start.astimezone(timezone.utc).strftime("%H%M") == "0700"
    assert slot.slot_id == "SLOT-20261012T0700Z01"


def test_zero_rows_render_fixed_line() -> None:
    assert SlotTable((), "en").render_markdown() == "No open slots in the next 7 days."
    assert SlotTable((), "es").render_markdown().startswith("No hay espacios libres")


def test_reply_embeds_table_and_disclaimer_verbatim() -> None:
    table = SlotTable(derive_open_slots(snapshot_with(), NOW, "Europe/Madrid", GRID), "es")
    reply = compose_slot_reply_text("Hola", table, "Elija uno")
    assert reply_embeds_table(reply, table)
    assert not reply_embeds_table(reply.replace("09:00", "10:00"), table)


def test_past_slots_of_today_are_not_offered() -> None:
    late = NOW.replace(hour=12)
    slots = derive_open_slots(snapshot_with(), late, "Europe/Madrid", GRID)
    assert [s.start_local for s in slots if s.local_date == "2026-10-12"] == [
        "13:00",
        "15:00",
        "17:00",
    ]


def test_morning_ends_at_noon_and_afternoon_starts_at_noon() -> None:
    slots = derive_open_slots(snapshot_with(), NOW, "Europe/Madrid", GRID)
    morning = filter_slots(slots, "2026-10-13", "2026-10-13", PartOfDay.MORNING)
    assert [s.start_local for s in morning] == ["09:00"]  # 11:00-13:00 crosses noon
    afternoon = filter_slots(slots, "2026-10-13", "2026-10-13", PartOfDay.AFTERNOON)
    assert [s.start_local for s in afternoon] == ["13:00", "15:00", "17:00"]
    assert len(filter_slots(slots, None, None, PartOfDay.MORNING)) == 7
    assert filter_slots(slots, None, None, PartOfDay.NONE) == slots


def test_filtered_empty_window_has_its_own_line() -> None:
    assert SlotTable((), "en", filtered=True).render_markdown().startswith("No open slots for")


def test_window_description_is_deterministic() -> None:
    assert describe_window("2026-10-13", "2026-10-13", PartOfDay.MORNING, "es") == (
        "2026-10-13, mañana (hasta las 12:00)"
    )
    assert describe_window(None, None, PartOfDay.NONE) == ""


def test_fallback_explains_ambiguity_and_names_no_slot() -> None:
    for reason in AmbiguityReason:
        reply = render_slot_fallback_reply("en", reason)
        assert "SLOT-" not in reply and "Please share your complete availability" in reply
    assert "exact time" in render_slot_fallback_reply("en", AmbiguityReason.UNSPECIFIED_TIME)


def test_outbound_guard_catches_internal_identifiers() -> None:
    from maintenance_agent.application.outbound_guard import leaks_internal_identifier

    for leak in (
        "pick SLOT-20261013T0700Z01",
        "slot_id abc",
        "counter:WO-1:2026-10-13T07:00:00+00:00",
        "id 0123456789abcdef",
    ):
        assert leaks_internal_identifier(leak)
    assert not leaks_internal_identifier("| 2026-10-13 | Tuesday | 09:00–11:00 | open |")


def _table() -> SlotTable:
    return SlotTable(derive_open_slots(snapshot_with(), NOW, "Europe/Madrid", GRID), "es")


def test_check_slot_prose_accepts_plain_sentences() -> None:
    assert check_slot_prose("Estas son las franjas del 2026-10-12.", "Elija una.", _table()) is None


def test_check_slot_prose_rejects_long_sentence() -> None:
    assert "Shorten" in (check_slot_prose("palabra " * 51, "Elija una.", _table()) or "")


def test_check_slot_prose_rejects_availability_promise() -> None:
    for text in ("Le garantizamos la visita.", "The technician will arrive on time."):
        assert check_slot_prose(text, "Elija una.", _table()) is not None


def test_check_slot_prose_rejects_date_outside_table() -> None:
    assert check_slot_prose("Hola", "Le va bien el 2027-01-01?", _table()) is not None


def test_check_slot_prose_rejects_time_outside_table() -> None:
    assert "times" in (check_slot_prose("Hola", "Le va bien a las 23:45?", _table()) or "")


def test_check_slot_prose_allows_times_echoed_from_the_window() -> None:
    window = "mañana (hasta las 12:00)"
    assert check_slot_prose("Hola", "Mañana hasta las 12:00?", _table(), window) is None
