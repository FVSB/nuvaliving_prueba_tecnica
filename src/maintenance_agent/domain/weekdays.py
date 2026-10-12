"""Single source of weekday names (English and Spanish) and their lookup by name."""

from datetime import date

WEEKDAYS_EN = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

WEEKDAYS_ES = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)

# Lower-cased names mapped to Monday=0 ... Sunday=6, including unaccented Spanish spellings.
WEEKDAY_INDEX: dict[str, int] = {
    **{name.lower(): index for index, name in enumerate(WEEKDAYS_EN)},
    **{name.lower(): index for index, name in enumerate(WEEKDAYS_ES)},
    "miercoles": 2,
    "sabado": 5,
}


def weekday_name_en(day: date) -> str:
    return WEEKDAYS_EN[day.weekday()]
