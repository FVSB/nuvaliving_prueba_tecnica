# Quickstart: Vague Date Request Handling with Deterministic Slot Table

**Feature**: 005-vague-slot-suggestion | **Date**: 2026-10-12

## Try it

1. Run the app (same delivery as Feature 004; `.env` with `ANTHROPIC_API_KEY`, CSV mount).
2. When a work order asks for availability, reply with a vague request instead of intervals:

```text
WO-002|tenant esta semana por la tarde que dias pueden ser?
```

3. Expected reply: short intro + deterministic markdown table of open two-hour slots for the
   next 7 days (agenda-open only, with the disclaimer) + ask to pick a slot or give explicit
   intervals — in the recognized tenant language. NOT the old generic
   "share your complete availability" prompt.
4. Reply with a concrete choice:

```text
WO-002|tenant el 2026-10-15 de 16:00 a 18:00
```

5. Negotiation continues exactly as in Feature 004 (candidates → handyman → proposal → decision).

## Fallback path

Force three validation failures (e.g. test double or flaky provider): after the 3rd composition
attempt the tenant receives the deterministic fallback reply — "be more specific", next open slot,
and the ask for explicit intervals. The order stays open and the next tenant message is processed
normally.

## Verify

```sh
uv run pytest
uv run pytest tests/acceptance -k slot
```

Check `/app/traces` JSONL for `slot_suggestion_attempt`, `slot_suggestion_feedback`, and
`slot_fallback_emitted` events.
