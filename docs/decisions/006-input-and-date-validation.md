# Decision 006: Input and Date Validation

**Date**: 2026-10-12
**Status**: Approved by user (visit hours and horizon handling)
**Scope**: `specs/006-validate-date-tool/` and synchronized clauses in `BUSINESS_RULES.md`

## Context

End-to-end exercises showed that the LLM's extracted dates reached the agenda unchecked (03:00
visits, year 2062, wrong weekdays, past dates), clarification answers were routed by the pending
action instead of the sender, and unknown, empty, or oversized messages were accepted.

## Decisions

1. **Visit hours**: the 09:00-19:00 `Europe/Madrid` slot grid is also the permitted visit window;
   both start and end of a visit must fall inside it. Chosen by the user.
2. **Horizon**: dates later than today plus `VISIT_HORIZON_DAYS` natural days (default 7) are rejected.
3. **Deterministic authority**: a pure `date_validation` tool (`DateCheck`, `DateErrorCode`,
   `validate_interval`, `validate_date_text`) validates every interval in code. The LLM remains
   evidence only (Constitution III).
4. **Order of checks**: deterministic validations first, LLM last. This amends spec 005 FR-005: the
   LLM pre-send validator is kept but runs after the deterministic checks and cannot override them.
5. **Rejections**: invalid dates are rejected with a short reason, traced as `availability_rejected`,
   and never recorded as availability. Messages for unknown work orders, empty, or longer than
   `MAX_MESSAGE_LENGTH` (default 2000) get a fixed reply and never reach an LLM.
6. **Cancellation**: a participant cancelling a pending proposal is treated as rejecting it.
7. **Already in place**: injection guard (3 passes, 0.6, fail open) and urgency only from the CSV.

8. **Horizon versus slot table (OD-001, resolved by the user)**: the 7-day horizon is not
   extended. The slot table is capped to the horizon (lookahead = horizon + 1 days) and the agent
   states how far it knows the agenda: "Solo conozco la disponibilidad hasta el {weekday_es}
   {YYYY-MM-DD}. Indíqueme una fecha dentro de ese límite." / "I only know the availability until
   {Weekday} {YYYY-MM-DD}. Please give me a date within that limit." A partly out-of-range window
   shows only the slots inside it plus that sentence; a window fully outside shows only the
   sentence and is traced as `slot_window_beyond_horizon`.
9. **Natural-language dates**: the LLM only extracts each mentioned date or time as components
   (`mentioned_dates`); code always validates them. Intervals outside 09:00-19:00 are rejected
   whole, never trimmed.
10. **Competing offers**: offering the same free slot to the handyman for two orders before a hold
    exists is allowed by `BUSINESS_RULES.md`; arbitration happens at hold creation and confirmed
    appointments are never preempted. A Low order may obtain the slot if it confirms first; this
    is accepted as a known risk, not a defect.

## Consequences

- `BUSINESS_RULES.md` gains only the minimal rules above; mechanics live in spec 006.
- No new settings beyond `VISIT_HORIZON_DAYS` and `MAX_MESSAGE_LENGTH`.
- Input rejections use fixed es/en replies (`application/rejections.py`; reasons `empty_body`,
  `too_long`, `unknown_work_order`, `protocol_mismatch`; bilingual `<en> / <es>` fallback). Trace
  events: `message_rejected` and `unknown_work_order` in `events.jsonl`; `malformed_input` and
  `message_rejected` (`protocol_mismatch`) in `runtime.jsonl`. Exact texts are in the spec.
