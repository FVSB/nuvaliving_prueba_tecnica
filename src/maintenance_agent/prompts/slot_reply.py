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


def build_slot_validate_prompt(reply: str, table_markdown: str, window: str, language: str) -> str:
    return (
        "Validate a drafted slot-suggestion reply before it is sent to a maintenance visit "
        "tenant. The reply layout is fixed by the system: an opening sentence, the table, a "
        "system-mandated disclaimer note directly under the table, then a closing sentence. "
        "The table and the disclaimer note are system text: never judge, shorten, or ask to "
        "remove them, and never count them as prose or as an availability promise. "
        "Return JSON with exactly two fields: valid (boolean) and feedback (string). "
        "Set valid to true only when all of the following hold: (1) the reply opens "
        "with a brief, clear sentence and closes with a brief, clear request asking the tenant "
        "to pick a slot or to state complete availability intervals with explicit dates and "
        "times (a sentence or two each is fine; do not reject for length unless it is "
        "rambling, roughly more than 50 words, or repeats itself); "
        "(2) the reply is written in the target language; (3) the reply does not claim, "
        "promise, or guarantee that the technician is available for any slot; (4) the reply "
        "does not invent dates, times, or availability beyond the supplied table; (5) the "
        "reply contains exactly one table and it is not duplicated. The deterministic table "
        "is supplied for comparison; byte-equality of the table is checked by the system "
        "separately, so judge only the prose around it. When in doubt about style or "
        "length, answer valid true; reject only for a wrong language, a promise of technician "
        "availability, invented dates or times, or a missing opening or closing request. When "
        "invalid, feedback must be one short actionable sentence naming what to fix.\n"
        f"Target language: {language}\n"
        f"Interpreted window: {json.dumps(window, ensure_ascii=False)}\n"
        f"Table:\n{table_markdown}\n"
        f"Drafted reply:\n{reply}"
    )
