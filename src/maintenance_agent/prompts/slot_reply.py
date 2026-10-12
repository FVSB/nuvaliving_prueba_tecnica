"""Prompts for slot-suggestion reply composition and validation (Feature 005)."""

import json


def build_slot_compose_prompt(
    language: str, table_markdown: str, window: str, feedback: str
) -> str:
    return (
        "Compose a slot-suggestion reply for a maintenance visit. Return JSON with exactly "
        "two string fields: intro and ask. intro is a brief, clear sentence (at most "
        "about 30 words) acknowledging the tenant's vague request and introducing the table. "
        "ask is a brief, clear sentence or two (at most about 40 words) asking the tenant to "
        "pick one slot by date and time, or to state complete availability intervals with "
        "explicit calendar dates and exact start and end times. Write both in the target "
        "language only. Never add example dates or times of your own. Never invent, promise, "
        "or guarantee any slot or technician availability; the table below is "
        "provided verbatim by the system and is not part of your output. Do not mention the word JSON. "
        "If feedback is non-empty, address it in your sentences.\n"
        f"Target language: {language}\n"
        f"Interpreted window: {json.dumps(window, ensure_ascii=False)}\n"
        f"Validator feedback: {json.dumps(feedback, ensure_ascii=False)}\n"
        f"Table (context only, do not reproduce):\n{table_markdown}"
    )


def build_language_detect_prompt(text: str) -> str:
    return (
        "Identify the language the text below is written in. Ignore proper names, numbers, "
        "dates and times. Return JSON with exactly one string field, language: the English "
        "name of the language in lowercase (for example 'english' or 'spanish').\n"
        f"Text:\n{json.dumps(text, ensure_ascii=False)}"
    )


def build_translate_prompt(text: str, language: str) -> str:
    return (
        f"Translate the text below into {language}. Keep the meaning and tone, and copy every "
        "date, time and number exactly as written. Do not add or remove information. Return "
        "only the translation.\n"
        f"Text:\n{text}"
    )
