# Contract: Deterministic Slot Table and Fallback Reply

**Feature**: 005-vague-slot-suggestion | **Date**: 2026-10-12

External behavior contract for the slot-suggestion node. All times render in the approved
`LOCAL_TIMEZONE` (default `Europe/Madrid`); comparisons use UTC.

## 1. Slot grid (presentation only)

- Window: 7 local days, starting at the reference day (day of the reference time in
  `LOCAL_TIMEZONE`), inclusive.
- Daily grid: consecutive two-hour slots from 09:00 to 19:00 local (final slot 17:00–19:00).
  These hours are presentation constants for suggestions only; they are not business hours and
  never filter tenant-supplied candidates.
- Past slots (start before the reference time) are never offered.
- Requested window: the interpreter agent resolves relative phrases with the deterministic
  `resolve_relative_range` tool (whole periods only; never past days), narrows them with the
  on-demand `relative-date-phrases` skill (index always injected, body read via `read_skill`),
  and returns an inclusive `date_from`/
  `date_to` plus `part_of_day`. The grid extends (max 35 days) to cover the requested range.
  Morning = slot ends by 12:00; afternoon = starts at or after 12:00; evening = starts at or after
  18:00. The table is filtered to that window (empty window renders a fixed localized line), and
  the reply states the interpreted window.
- Open slot: a grid slot overlapping no confirmed appointment and no tentative hold in the
  shared-agenda snapshot. Occupancy is the only claim the table makes.

## 2. Slot table (deterministic rendering)

Fixed format, byte-identical for identical snapshot + reference time:

```markdown
| Slot   | Date         | Day        | Time (local) | Status |
|--------|--------------|------------|--------------|--------|
| SLOT-<id> | YYYY-MM-DD | <Weekday> | HH:MM–HH:MM | open   |
```

- Ordering: by UTC start, then slot ID.
- `Slot` = `SLOT-<YYYYMMDDTHHMMZ><ordinal>` (stable for the same slot).
- Rows: every open slot in the window; zero rows renders the fixed line
  `No open slots in the next 7 days.` instead of the table body.
- Fixed disclaimer, always present, verbatim after the table:

```text
Note: "open" means free in the shared work schedule only; it does not guarantee the
technician is available. A visit lasts two hours.
```

Localized per tenant language (recognized language for the work order; handyman always Spanish,
but this node only addresses the tenant).

The table block is produced by deterministic code and injected verbatim into the composed reply;
the LLM never regenerates it.

## 3. Composed slot-suggestion reply (LLM prose + deterministic table)

Structure: short intro sentence (LLM) + table block (verbatim) + one closing ask (LLM, must
request explicit intervals or a slot pick). Validation requires: intro and ask present, table
block byte-equal to the deterministic rendering, disclaimer present, language matching the
recognized tenant language, and no availability/consent claims beyond the table.

## 4. Validation verdict (pre-send gate)

Validator input: drafted reply, deterministic table, occupancy data from the snapshot. Output
(structured): `valid: bool`, `feedback: str`. Deterministic pre-checks (table byte match, slot
openness recomputation) run first; a failed pre-check is an invalid verdict with generated
feedback. The reply is sent only on `valid: true`. Invalid → feedback appended to composer prompt
→ regenerate. Hard cap: 3 composition attempts per inbound tenant message; on the 3rd failure the
fallback reply is emitted instead.

## 5. Fallback reply (deterministic, no LLM, no slots)

Localized template, fixed order, chosen by the classifier's `ambiguity_reason`
(`unspecified_time`, `unspecified_day`, `ambiguous_am_pm`, `other`):

1. One sentence explaining why the request was ambiguous.
2. The standard ask for explicit availability intervals (dates plus start and end times).

The fallback never names or hints at any open slot.

## 6. Trace events

Per `BUSINESS_RULES.md` JSONL rules (`/app/traces`): `slot_suggestion_attempt`,
`slot_suggestion_feedback`, `slot_fallback_emitted` — each with timestamp, work-order ID, event
type, and detail (attempt number, row count, feedback text, or next slot).

## 7. Non-goals

- The table is never availability evidence, candidate input, consent, or handyman availability.
- No new terminal status, CLI format, CSV change, or message protocol change; Feature 004
  contracts are untouched.
