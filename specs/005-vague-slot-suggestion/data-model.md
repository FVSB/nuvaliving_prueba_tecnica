# Data Model: Vague Date Request Handling with Deterministic Slot Table

**Feature**: 005-vague-slot-suggestion | **Date**: 2026-10-12

## New domain values

- `GraphCursor.SLOT_SUGGESTION = "slot_suggestion"` — active while the slot-suggestion node owns
  the turn; reverts to tenant-availability pending state before awaiting the next tenant message.
- `PendingAction.SLOT_SUGGESTION = "slot_suggestion"` and
  `PendingAction.SLOT_FALLBACK = "slot_fallback"` — pending-question actions for the two new
  reply kinds; both keep `role = tenant`.

## New typed structures (application layer, frozen dataclasses / Pydantic where validated)

- `MessageClass` (closed enum): `EXPLICIT_INTERVALS`, `VAGUE_DATE_REQUEST`, `DECISION`,
  `UNCLASSIFIED`. Returned by the extended availability interpretation.
- `SlotGridSpec` (frozen): `lookahead_days = 7`, `daily_start_hour`, `daily_end_hour`,
  `slot_hours = 2`, `timezone_name`. Loaded from approved settings at composition root; constants
  documented in contracts/slot-table.md.
- `OpenSlot` (frozen): `slot_id` (stable, e.g. `SLOT-<UTC start compact>-<index>`), `start_utc`,
  `end_utc`, `local_date`, `weekday_label`, `start_local`, `end_local`, `status = "open"`.
- `SlotTable` (frozen): `slots: tuple[OpenSlot, ...]`, `disclaimer_key`; renders via a single
  deterministic `render_markdown()` — fixed columns, ordering by `start_utc` then `slot_id`.
- `ValidationVerdict` (Pydantic-validated LLM output): `valid: bool`, `feedback: str | None`,
  plus deterministic pre-check results (table byte match, slot openness recomputation).
- `RetryCounter`: plain int in workflow state; `composition_attempts` per inbound tenant message;
  reset on every new tenant message; hard cap 3.

## Extended structures

- `AvailabilityInterpretation` (application/conversation.py): new fields
  `classification: MessageClass = UNCLASSIFIED` and `next_open_slot_hint: TimeInterval | None`
  (deterministic, may be recomputed by the node itself instead).
- `ScheduleSnapshot` usage: unchanged shape; the slot-suggestion node derives `OpenSlot` tuples
  only from `snapshot.appointments` and `snapshot.holds` (occupancy), never from evidence claims.
- Workflow state dict: new keys `slot_retry_attempts: int`, `message_classification: MessageClass`,
  `last_validation_feedback: str | None`. No changes to `tenant_evidence`, `handyman_evidence`,
  `candidates`, `proposal`, `decisions`, or terminal fields.

## State transitions (availability phase, per inbound tenant message)

```text
tenant msg ──▶ classify
  ├─ EXPLICIT_INTERVALS ─▶ existing branches (relative-date confirm / dispute / record)
  ├─ VAGUE_DATE_REQUEST ─▶ SLOT_SUGGESTION node
  │      snapshot ─▶ derive SlotTable ─▶ deterministic pre-check
  │      ├─ pass ─▶ compose (LLM, table injected verbatim) ─▶ validate (LLM + pre-check)
  │      │     ├─ valid ─▶ send reply ─▶ pending: TENANT availability (normal graph continues)
  │      │     └─ invalid ─▶ feedback ─▶ recompose (attempt 2, 3)
  │      │           └─ 3rd failure ─▶ SLOT_FALLBACK: deterministic reply ─▶ send
  │      └─ (loop is per-message; counter resets on next tenant message)
  └─ DECISION / UNCLASSIFIED ─▶ existing clarification branch
```

The fallback state is not a `TerminalStatus`; the order stays non-terminal and the pending
question remains the tenant availability question.

## Trace events (JSONL, per BUSINESS_RULES.md)

- `slot_suggestion_attempt` — timestamp, work_order_id, attempt number, table row count,
  validation outcome.
- `slot_suggestion_feedback` — timestamp, work_order_id, attempt number, validator feedback text.
- `slot_fallback_emitted` — timestamp, work_order_id, ambiguity reason (no slot is shared).
