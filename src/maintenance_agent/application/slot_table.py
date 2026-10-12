"""Deterministic agenda-open slot table for vague date requests (Feature 005)."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from maintenance_agent.application.conversation import AmbiguityReason, PartOfDay
from maintenance_agent.domain.negotiation import TimeInterval


@dataclass(frozen=True, slots=True)
class SlotGridSpec:
    """Presentation-only grid constants; never candidate or consent evidence."""

    lookahead_days: int = 7
    daily_start_hour: int = 9
    daily_end_hour: int = 19
    slot_hours: int = 2


@dataclass(frozen=True, slots=True)
class OpenSlot:
    """One grid slot that overlaps no appointment or hold in the shared agenda."""

    slot_id: str
    interval: TimeInterval
    local_date: str
    weekday: str
    start_local: str
    end_local: str


_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

_DISCLAIMERS = {
    "es": (
        "Nota: «libre» significa únicamente libre en la agenda de trabajo compartida; "
        "no garantiza que el técnico esté disponible. Una visita dura dos horas."
    ),
    "en": (
        "Note: \"open\" means free in the shared work schedule only; it does not guarantee "
        "the technician is available. A visit lasts two hours."
    ),
}

_NO_SLOTS = {
    "es": "No hay espacios libres en los próximos 7 días.",
    "en": "No open slots in the next 7 days.",
}

_NO_SLOTS_WINDOW = {
    "es": "No hay espacios libres para el día y la franja solicitados.",
    "en": "No open slots for the requested day and time of day.",
}

_FALLBACK_REASON = {
    AmbiguityReason.UNSPECIFIED_TIME: {
        "es": "No pude determinar una hora exacta a partir de su mensaje.",
        "en": "I could not determine an exact time from your message.",
    },
    AmbiguityReason.UNSPECIFIED_DAY: {
        "es": "No pude determinar un día concreto a partir de su mensaje.",
        "en": "I could not determine a specific day from your message.",
    },
    AmbiguityReason.AMBIGUOUS_AM_PM: {
        "es": "La hora indicada es ambigua (no queda claro si es de la mañana o de la tarde).",
        "en": "The time you gave is ambiguous (it is unclear whether it is morning or evening).",
    },
    AmbiguityReason.OTHER: {
        "es": "Su mensaje no indica una fecha y hora concretas.",
        "en": "Your message does not give a specific date and time.",
    },
}

_FALLBACK_ASK = {
    "es": (
        "Por favor, indíquenos sus intervalos de disponibilidad completos, con fechas de "
        "calendario explícitas y horarios exactos (por ejemplo: del 14 de marzo de 2026, "
        "de 9:00 a 11:30)."
    ),
    "en": (
        "Please share your complete availability intervals, with explicit calendar dates "
        "and exact times (for example: March 14, 2026, 9:00 to 11:30)."
    ),
}

_PART_LABEL = {
    PartOfDay.MORNING: {"es": "mañana (hasta las 12:00)", "en": "morning (until 12:00)"},
    PartOfDay.AFTERNOON: {"es": "tarde (desde las 12:00)", "en": "afternoon (from 12:00)"},
    PartOfDay.EVENING: {"es": "noche (desde las 18:00)", "en": "evening (from 18:00)"},
}


@dataclass(frozen=True, slots=True)
class SlotTable:
    """Deterministic open-slot table; ordered by UTC start then slot ID."""

    slots: tuple[OpenSlot, ...]
    language: str = "en"
    filtered: bool = False

    def render_markdown(self) -> str:
        ordered = tuple(sorted(self.slots, key=lambda slot: (slot.interval.start, slot.slot_id)))
        if not ordered and self.filtered:
            return _NO_SLOTS_WINDOW.get(self.language, _NO_SLOTS_WINDOW["en"])
        return render_slot_table(ordered, self.language)

    def disclaimer(self) -> str:
        return slot_disclaimer(self.language)


def _overlaps(left: TimeInterval, right: TimeInterval) -> bool:
    return left.start < right.end and right.start < left.end


def derive_open_slots(
    snapshot, reference_time: datetime, timezone_name: str, grid: SlotGridSpec
) -> tuple[OpenSlot, ...]:
    """Derive the presentation grid slots not occupied in the shared agenda snapshot."""
    zone = ZoneInfo(timezone_name)
    occupied = tuple(appointment.interval for appointment in snapshot.appointments) + tuple(
        hold.interval for hold in snapshot.holds
    )
    local_reference = reference_time.astimezone(zone)
    day = local_reference.date()
    slots: list[OpenSlot] = []
    for day_offset in range(grid.lookahead_days):
        current = day + timedelta(days=day_offset)
        start_hour = grid.daily_start_hour
        while start_hour + grid.slot_hours <= grid.daily_end_hour:
            start_local = datetime.combine(current, time(start_hour), tzinfo=zone)
            end_local = datetime.combine(
                current, time(start_hour + grid.slot_hours), tzinfo=zone
            )
            interval = TimeInterval(start_local, end_local)
            if start_local < local_reference:
                start_hour += grid.slot_hours
                continue
            if not any(_overlaps(interval, item) for item in occupied):
                slots.append(
                    OpenSlot(
                        _slot_id(interval),
                        interval,
                        current.isoformat(),
                        _WEEKDAYS[start_local.weekday()],
                        start_local.strftime("%H:%M"),
                        end_local.strftime("%H:%M"),
                    )
                )
            start_hour += grid.slot_hours
    return tuple(slots)


def _slot_id(interval: TimeInterval) -> str:
    stamp = interval.start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M") + "Z"
    return f"SLOT-{stamp}01"


def render_slot_table(slots: tuple[OpenSlot, ...], language: str = "en") -> str:
    """Render the fixed markdown table (or the fixed zero-row line)."""
    if not slots:
        return _NO_SLOTS.get(language, _NO_SLOTS["en"])
    header = (
        "| Slot   | Date         | Day        | Time (local) | Status |\n"
        "|--------|--------------|------------|--------------|--------|"
    )
    rows = [
        f"| {slot.slot_id} | {slot.local_date:<12} | {slot.weekday:<10} | "
        f"{slot.start_local}–{slot.end_local} | open   |"
        for slot in slots
    ]
    return "\n".join((header, *rows))


def slot_disclaimer(language: str = "en") -> str:
    return _DISCLAIMERS.get(language, _DISCLAIMERS["en"])


def filter_slots(
    slots: tuple[OpenSlot, ...],
    date_from: str | None,
    date_to: str | None,
    part_of_day: PartOfDay,
) -> tuple[OpenSlot, ...]:
    """Keep slots inside the requested inclusive local date range and part of day."""

    def keep(slot: OpenSlot) -> bool:
        if date_from and slot.local_date < date_from:
            return False
        if date_to and slot.local_date > date_to:
            return False
        start, end = slot.start_local, slot.end_local
        if part_of_day is PartOfDay.MORNING:
            return end <= "12:00"
        if part_of_day is PartOfDay.AFTERNOON:
            return start >= "12:00"
        if part_of_day is PartOfDay.EVENING:
            return start >= "18:00"
        return True

    return tuple(slot for slot in slots if keep(slot))


def describe_window(
    date_from: str | None,
    date_to: str | None,
    part_of_day: PartOfDay,
    language: str = "en",
) -> str:
    """Deterministic description of the interpreted request, shown to the tenant."""
    parts = []
    if date_from and date_to and date_from != date_to:
        parts.append(f"{date_from} → {date_to}")
    elif date_from or date_to:
        parts.append(date_from or date_to or "")
    if part_of_day is not PartOfDay.NONE:
        parts.append(_PART_LABEL[part_of_day].get(language, _PART_LABEL[part_of_day]["en"]))
    return ", ".join(parts)


def render_slot_fallback_reply(language: str, reason: AmbiguityReason) -> str:
    """Deterministic third-retry fallback: explain the ambiguity, name no slots, no LLM."""
    explanation = _FALLBACK_REASON[reason].get(language, _FALLBACK_REASON[reason]["en"])
    ask = _FALLBACK_ASK.get(language, _FALLBACK_ASK["en"])
    return f"{explanation}\n{ask}"


def compose_slot_reply_text(intro: str, table: SlotTable, ask: str) -> str:
    """Join LLM prose around the verbatim deterministic table and disclaimer."""
    return f"{intro.strip()}\n\n{table.render_markdown()}\n{table.disclaimer()}\n\n{ask.strip()}"


def reply_embeds_table(reply: str, table: SlotTable) -> bool:
    """Deterministic pre-check: table block and disclaimer appear verbatim."""
    return table.render_markdown() in reply and table.disclaimer() in reply
