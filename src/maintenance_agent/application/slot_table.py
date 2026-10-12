"""Deterministic agenda-open slot table for vague date requests (Feature 005)."""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from maintenance_agent.application.conversation import AmbiguityReason, PartOfDay
from maintenance_agent.domain.negotiation import TimeInterval
from maintenance_agent.domain.scheduling import overlaps
from maintenance_agent.domain.weekdays import WEEKDAYS_EN, WEEKDAYS_ES


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


_DISCLAIMERS = {
    "es": (
        "Nota: estos horarios están libres únicamente en la agenda de trabajo compartida; "
        "no garantiza que el técnico esté disponible. Una visita dura dos horas."
    ),
    "en": (
        "Note: these times are free in the shared work schedule only; it does not guarantee "
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

_REQUESTED_TAKEN = {
    "confirmed": {
        "es": "Ese horario ya no está disponible: está reservado para otra visita confirmada.",
        "en": "That time is no longer available: it is booked for another confirmed visit.",
    },
    "held": {
        "es": (
            "Ese horario no está disponible ahora: está retenido para otra visita "
            "de igual o mayor prioridad."
        ),
        "en": (
            "That time is not available right now: it is held for another visit of equal "
            "or higher priority."
        ),
    },
    "infeasible": {
        "es": "Ese horario no está disponible: la visita no cabe en esa franja.",
        "en": "That time is not available: the visit does not fit in that window.",
    },
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

_FALLBACK_TABLE_ASK = {
    "es": (
        "Indíquenos qué día y hora de la tabla prefiere, o su disponibilidad completa con "
        "fechas de calendario y horarios exactos."
    ),
    "en": (
        "Please tell us which date and time from the table you prefer, or share your complete "
        "availability with explicit calendar dates and exact times."
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
            end_local = datetime.combine(current, time(start_hour + grid.slot_hours), tzinfo=zone)
            interval = TimeInterval(start_local, end_local)
            if start_local < local_reference:
                start_hour += grid.slot_hours
                continue
            if not any(overlaps(interval, item) for item in occupied):
                slots.append(
                    OpenSlot(
                        _slot_id(interval),
                        interval,
                        current.isoformat(),
                        WEEKDAYS_EN[start_local.weekday()],
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
        "| Date         | Day        | Time (local) |\n|--------------|------------|--------------|"
    )
    rows = [
        f"| {slot.local_date:<12} | {slot.weekday:<10} | {slot.start_local}–{slot.end_local} |"
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


def render_requested_taken(language: str, cause: str = "confirmed") -> str:
    texts = _REQUESTED_TAKEN.get(cause, _REQUESTED_TAKEN["confirmed"])
    return texts.get(language, texts["en"])


def render_slot_fallback_reply(language: str, reason: AmbiguityReason) -> str:
    """Deterministic third-retry fallback: explain the ambiguity, name no slots, no LLM."""
    explanation = _FALLBACK_REASON[reason].get(language, _FALLBACK_REASON[reason]["en"])
    ask = _FALLBACK_ASK.get(language, _FALLBACK_ASK["en"])
    return f"{explanation}\n{ask}"


def render_slot_fallback_table_reply(table: SlotTable, reason: AmbiguityReason) -> str:
    """Fixed localized reply with the deterministic table, used when the prose attempts fail."""
    language = table.language
    if not table.slots:
        return table.render_markdown()
    intro = _FALLBACK_REASON[reason].get(language, _FALLBACK_REASON[reason]["en"])
    ask = _FALLBACK_TABLE_ASK.get(language, _FALLBACK_TABLE_ASK["en"])
    return compose_slot_reply_text(intro, table, ask)


def compose_slot_reply_text(intro: str, table: SlotTable, ask: str) -> str:
    """Join LLM prose around the verbatim deterministic table and disclaimer."""
    return f"{intro.strip()}\n\n{table.render_markdown()}\n{table.disclaimer()}\n\n{ask.strip()}"


_PROSE_MAX_WORDS = 50
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_AVAILABILITY_PROMISE = re.compile(
    r"garantiz\w*|guarant\w*|prometemos|we promise|"
    r"t[eé]cnico (?:estar[aá]|llegar[aá]|acudir[aá])|technician (?:will|is sure)",
    re.IGNORECASE,
)


def check_slot_prose(intro: str, ask: str, table: SlotTable, window: str = "") -> str | None:
    """Cheap deterministic pre-check of the LLM prose; return actionable feedback or None."""
    for label, text in (("opening", intro), ("closing", ask)):
        if len(text.split()) > _PROSE_MAX_WORDS:
            return f"Shorten the {label} sentence to at most {_PROSE_MAX_WORDS} words."
        if _AVAILABILITY_PROMISE.search(text):
            return f"The {label} sentence must not promise or guarantee technician availability."
    if table.slots:
        listed = {slot.local_date for slot in table.slots}
        for text in (intro, ask):
            if any(day not in listed for day in _ISO_DATE.findall(text)):
                return "Mention only dates that appear in the table."
        # The interpreted window ("mañana, hasta las 12:00") may legitimately be echoed back.
        listed_times = {
            (int(h), int(m)) for h, m in _CLOCK.findall(f"{table.render_markdown()}\n{window}")
        }
        for text in (intro, ask):
            if any((int(h), int(m)) not in listed_times for h, m in _CLOCK.findall(text)):
                return "Mention only times that appear in the table."
    return None


def reply_embeds_table(reply: str, table: SlotTable) -> bool:
    """Deterministic pre-check: table block and disclaimer appear verbatim."""
    return table.render_markdown() in reply and table.disclaimer() in reply


_WEEKDAY_WORDS = {
    "monday": "Monday",
    "lunes": "Monday",
    "tuesday": "Tuesday",
    "martes": "Tuesday",
    "wednesday": "Wednesday",
    "miercoles": "Wednesday",
    "miércoles": "Wednesday",
    "thursday": "Thursday",
    "jueves": "Thursday",
    "friday": "Friday",
    "viernes": "Friday",
    "saturday": "Saturday",
    "sabado": "Saturday",
    "sábado": "Saturday",
    "sunday": "Sunday",
    "domingo": "Sunday",
}
_WEEKDAY_PATTERN = re.compile(r"\b(" + "|".join(_WEEKDAY_WORDS) + r")\b", re.IGNORECASE)
_DAY_PATTERN = re.compile(
    r"\b(?:el|the|day)\s+(\d{1,2})(?:st|nd|rd|th)?\b(?!\s*[:h])", re.IGNORECASE
)
_MONTH_PATTERN = re.compile(
    r"\b(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|"
    r"noviembre|diciembre|january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\b",
    re.IGNORECASE,
)
_HOUR_PATTERN = re.compile(r"\b(?:a\s+las?|at|@)\s*(\d{1,2})(?::(\d{2}))?\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TableReference:
    """What a reply names about an already displayed slot table; every field is optional."""

    weekday: str | None = None
    day_of_month: int | None = None
    hour: int | None = None

    def __bool__(self) -> bool:
        return any(value is not None for value in (self.weekday, self.day_of_month, self.hour))


def parse_table_reference(text: str) -> TableReference:
    """Extract a weekday, day of month and start hour from a short reply, without any model."""
    weekday = _WEEKDAY_PATTERN.search(text)
    day = None if _MONTH_PATTERN.search(text) else _DAY_PATTERN.search(text)
    hour = _HOUR_PATTERN.search(text)
    return TableReference(
        _WEEKDAY_WORDS[weekday.group(1).lower()] if weekday else None,
        int(day.group(1)) if day else None,
        int(hour.group(1)) if hour else None,
    )


def _reference_hours(hour: int | None, start_hour: int, end_hour: int) -> set[int]:
    """24h readings of a bare hour: the single one inside the visit window, or none."""
    if hour is None:
        return set()
    if hour >= 12:
        return {hour}
    resolved = _resolve_bare_hour(hour, start_hour, end_hour)
    return {resolved} if resolved is not None else set()


def _resolve_bare_hour(hour: int, start_hour: int, end_hour: int) -> int | None:
    readings = [value for value in (hour, hour + 12) if start_hour <= value < end_hour]
    return readings[0] if len(readings) == 1 else None


def match_table_reference(
    slots: tuple[OpenSlot, ...],
    reference: TableReference,
    start_hour: int = 9,
    end_hour: int = 19,
) -> tuple[OpenSlot, ...]:
    """Shown slots consistent with the reference; a bare hour is read inside the visit window."""
    hours = _reference_hours(reference.hour, start_hour, end_hour)

    def keep(slot: OpenSlot) -> bool:
        if reference.weekday is not None and slot.weekday != reference.weekday:
            return False
        day = int(slot.local_date[-2:])
        if reference.day_of_month is not None and day != reference.day_of_month:
            return False
        if reference.hour is None:
            return True
        start = int(slot.start_local[:2])
        end = int(slot.end_local[:2])
        return any(start <= hour < end for hour in hours)

    return tuple(slot for slot in slots if keep(slot))


_HORIZON_LIMIT = {
    "es": "Solo conozco la disponibilidad hasta el {weekday} {date}. "
    "Indíqueme una fecha dentro de ese límite.",
    "en": "I only know the availability until {weekday} {date}. "
    "Please give me a date within that limit.",
}


def render_horizon_limit(language: str, last_known: date) -> str:
    """Deterministic statement of how far the agenda is known, asking for an earlier date."""
    weekday = (WEEKDAYS_ES if language == "es" else WEEKDAYS_EN)[last_known.weekday()]
    template = _HORIZON_LIMIT.get(language, _HORIZON_LIMIT["en"])
    return template.format(weekday=weekday, date=last_known.isoformat())


def format_local_date(day: date, language: str) -> str:
    """Date with its correct weekday, e.g. 'Lunes 2026-10-12' / 'Monday 2026-10-12'."""
    names = WEEKDAYS_ES if language == "es" else WEEKDAYS_EN
    return f"{names[day.weekday()]} {day.isoformat()}"


def resolve_reference_dates(reference: TableReference, today: date) -> tuple[str, str] | None:
    """Next calendar day named by a weekday or day-of-month reply (possibly past the horizon)."""
    if reference.weekday is None and reference.day_of_month is None:
        return None
    first = 1 if reference.day_of_month is None else 0
    for offset in range(first, 70):
        day = today + timedelta(days=offset)
        if reference.weekday is not None and WEEKDAYS_EN[day.weekday()] != reference.weekday:
            continue
        if reference.day_of_month is not None and day.day != reference.day_of_month:
            continue
        return day.isoformat(), day.isoformat()
    return None
