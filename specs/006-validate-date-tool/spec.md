# Feature Specification: Deterministic Date, Role, and Input Validation Fixes

**Feature Branch**: `006-validate-date-tool` (no git branch created; work continues on `005-vague-slot-suggestion`)
**Created**: 2026-10-12
**Status**: Implemented (pending verification package V)
**Input**: Bug-fix batch found while exercising the agent end to end: invalid dates (03:00 visits,
year 2062, wrong weekday, past dates) accepted as availability; tenant clarification answers routed
as handyman answers; no way to cancel or correct availability; unknown work orders and empty or
oversized messages accepted; rejected lines not reported to the sender; slot-table follow-ups not
linked to the displayed slots; thinking blocks exhausting `max_tokens`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deterministic date and visit-hours validation (Priority: P1)

Every availability interval or date the LLM extracts from a participant message is validated by a
deterministic `date_validation` tool before it can become availability evidence. Invalid dates are
rejected with a short English reason, the sender is asked again, and the rejection is traced.

**Why this priority**: Today a 03:00 visit, a 2062 date, or a past date is silently recorded as
availability, which can lead to a `scheduled` result for an impossible visit.

**Independent Test**: Send `WO-001|tenant el 13 de octubre a las 03:00`; the reply states that visits
run 09:00-19:00 and asks for another time; `events.jsonl` has `availability_rejected` with code
`outside_visit_hours`; no interval is stored.

**Acceptance Scenarios**:

1. **Given** the reference time 2026-10-12T12:00:00+02:00, **When** a participant offers 03:00-05:00
   on 2026-10-13, **Then** the interval is rejected as `outside_visit_hours`, nothing is recorded as
   availability, and the sender receives the reason and a re-ask.
2. **Given** a date in 2062, **When** validated, **Then** it is rejected as `too_far_ahead`.
3. **Given** "lunes 14 de octubre" where 14 October 2026 is a Wednesday, **When** validated, **Then**
   it is rejected as `weekday_mismatch` with `actual_weekday` set to the real weekday.
4. **Given** a date or time earlier than the reference time, **Then** it is rejected as `in_the_past`.
5. **Given** a non-existent date (30 February) or time (25:00), **Then** it is rejected as
   `not_a_calendar_date` or `invalid_time`.
6. **Given** a handyman availability reply with an invalid date, **Then** the same validation and
   rejection path applies (not only tenant replies).
7. **Given** a re-ask message, **Then** it contains no hard-coded example dates from past years and
   is consistent with the extracted `date_from`/`date_to`.

---

### User Story 2 - Correct role routing and cancellation (Priority: P1)

A clarification answer is processed according to the role that sent it, not the action of the
pending question. Participants can cancel or correct previously given availability. A handyman's
natural acceptance containing the date and time counts as acceptance. `<NO RESPONSE>` names the
silent role correctly. The same attribution applies to the reminders and the final REASON of 004's RETRYING rule (the silent role is the role owed the pending answer, not necessarily the sentinel sender).

**Independent Test**: After a tenant clarification, the tenant's answer is processed on the tenant
path; a tenant who answers "cancela" to a proposal triggers a rejection of that proposal.

**Acceptance Scenarios**:

1. **Given** a clarification asked to the tenant, **When** the tenant answers, **Then** the answer is
   handled as tenant input (never as handyman availability).
2. **Given** a pending proposal, **When** the tenant says they cancel, **Then** it is treated as a
   rejection of the proposal and negotiation continues per the existing rejection rules.
3. **Given** previously given availability, **When** a participant corrects it, **Then** the
   reversal rule of `docs/BUSINESS_RULES.md` (sender confirmation, previous value preserved) applies.
4. **Given** the handyman writes "Sí, me viene bien el 13 de octubre de 9:00 a 11:00" for the open
   proposal, **Then** it counts as acceptance of that proposal (still validated by code).
5. **Given** `<NO RESPONSE>` from a role, **Then** the `requires_review` reason names that role.

---

### User Story 3 - Inbound input validation (Priority: P2)

Inbound lines that cannot be processed are rejected before any worker or LLM call and the sender
receives a fixed reply when the sender can be identified.

**Acceptance Scenarios**:

1. **Given** `WO-999|tenant hola` with WO-999 not in the CSV, **Then** no worker is created and the
   sender receives a fixed rejection (unknown work order).
2. **Given** an empty body, **Then** it is rejected with a fixed reply.
3. **Given** a body longer than `MAX_MESSAGE_LENGTH` (default 2000), **Then** it is rejected with a
   fixed reply and never reaches an LLM.
4. **Given** a line without `|` or with an invalid role (for example `admin`), **Then** it is
   ignored, logged to `runtime.jsonl` as `malformed_input` as before plus a `message_rejected`
   event with `reason: protocol_mismatch` (`length`, `input_preview`), and nobody is answered
   because no sender can be identified. A line with a valid work order id and role but an empty
   or oversized body, or an unknown work order id, is answered (`WO-001|tenant` with no body is
   `empty_body`).

**Fixed rejection replies** (`application/rejections.py`; only `es` and `en` templates exist; the
tenant gets its recognized language, the handyman gets Spanish, and an unknown language or work
order gets the bilingual `<en> / <es>` form):

| Reason | Spanish | English |
|---|---|---|
| `empty_body` | Su mensaje está vacío y no se ha procesado. Envíe un mensaje con contenido. | Your message is empty and was not processed. Please send a message with content. |
| `too_long` | Su mensaje supera el máximo de {limit} caracteres y no se ha procesado. | Your message exceeds the maximum of {limit} characters and was not processed. |
| `unknown_work_order` | La orden de trabajo indicada no existe y el mensaje no se ha procesado. | The indicated work order does not exist and the message was not processed. |

Length is measured on the body. Trace events: `events.jsonl` `message_rejected` with detail
`{reason, sent_work_order_id, role, length, body_preview (first 200 characters)}`, and for unknown
work orders additionally `unknown_work_order` with `{sent_work_order_id, role, length}`; both carry
`work_order_id: null`.

---

### User Story 4 - Slot suggestion follow-ups and overlap (Priority: P2)

After the slot table is shown, a reply such as "el viernes" is bound to the displayed slots. The same
time slot is not offered to two work orders before a hold exists.

**Acceptance Scenarios**:

1. **Given** a displayed slot table, **When** the tenant replies "el viernes", **Then** the choice is
   resolved against the displayed slots and validated deterministically; if ambiguous, a
   clarification is asked.
2. **Given** two work orders receiving suggestions concurrently, **Then** a deterministic test shows
   whether the same free slot can be offered to both (investigation first; fix only if confirmed).
   Outcome: allowed by `docs/BUSINESS_RULES.md`; no code change (see Known Risks).

---

### Edge Cases

- Visit crossing a boundary: 18:00-20:00 is outside visit hours (start and end must be inside 09-19).
- Day equal to `today + horizon_days` is valid; the next day is `too_far_ahead`.
- A date today earlier than `now` is `in_the_past`.
- DST transition days follow the existing deferral rule (no new DST policy).
- LLM output exhausting `max_tokens` because of a `thinking` block must be diagnosable
  (`LlmOutputError`) and thinking is disabled for structured calls.
- A vague request ("la semana que viene") interacts with the horizon; the table is capped to the horizon and the limit sentence is shown (OD-001, resolved).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a pure, injectable `date_validation` module in `domain/`
  with `DateErrorCode` (`not_a_calendar_date`, `invalid_time`, `in_the_past`, `weekday_mismatch`,
  `too_far_ahead`, `outside_visit_hours`), the frozen result `DateCheck(valid, code, reason,
  actual_weekday, nearest_valid)`, and the two entry points
  `validate_interval(interval, now, timezone_name, *, start_hour, end_hour, horizon_days)` and
  `validate_date_text(date, time, claimed_weekday, now, timezone_name, *, start_hour, end_hour,
  horizon_days)`. It MUST read no global state or clock.
- **FR-002**: Visits MUST fall entirely (start and end) within local 09:00-19:00 `Europe/Madrid`
  (`SLOT_DAILY_START_HOUR`/`SLOT_DAILY_END_HOUR`); this is a binding rule, not only a presentation grid.
- **FR-003**: A date whose local day is later than today plus `VISIT_HORIZON_DAYS` natural days
  (default 7) MUST be rejected as `too_far_ahead`; an instant before `now` as `in_the_past`.
- **FR-004**: A claimed weekday that disagrees with the calendar date MUST be rejected as
  `weekday_mismatch`, reporting `actual_weekday`.
- **FR-005**: `validate_interval` MUST be applied by code as a safety net to every interval before it
  is stored, for both tenant and handyman, regardless of what the LLM interpretation claims.
  The interpretation carries `invalid_reason: DateCheck | None`.
- **FR-006**: Each rejection MUST be traced as `availability_rejected` with detail
  `{actor, code, reason, input, proposed}` and MUST send the sender the reason and a re-ask; no
  availability is recorded.
- **FR-007**: Validation order is fixed: deterministic checks first (input size/emptiness/known work
  order, injection guard, date validation), LLM stages last. The LLM is evidence only and never
  authority (Constitution III).
- **FR-008** (amends spec 005 FR-005): The pre-send LLM validator of slot-suggestion replies is
  retained, but it runs only after the deterministic checks (table rendering, agenda openness,
  date validity) have passed. A reply failing a deterministic check is never sent regardless of
  the LLM verdict, and an LLM approval never overrides a deterministic failure.
- **FR-009**: Inbound messages for unknown work orders, with empty bodies, or longer than
  `MAX_MESSAGE_LENGTH` (default 2000, settings validated > 0) MUST be rejected before creating
  workers or invoking LLMs, with a fixed reply to the sender.
- **FR-010**: A clarification answer MUST be dispatched by sender role. The pending action of the
  question MUST NOT determine how the reply is interpreted.
- **FR-011**: A participant cancellation of a pending proposal MUST be treated as rejection of that
  proposal; corrections follow the existing reversal rule.
- **FR-012**: A handyman message that explicitly accepts and restates the same date and time of the
  open proposal MUST count as acceptance; code verifies the restated interval matches.
- **FR-013**: `<NO RESPONSE>` handling MUST attribute the silence to the sending role.
- **FR-014**: Replies to the slot table MUST be resolved against the displayed slots and validated
  deterministically before use.
- **FR-015**: The same free slot MUST NOT be offered as a candidate to two orders when a hold
  already exists; behavior before a hold exists is first established by a deterministic test.
- **FR-016** (already implemented): The prompt-injection guard runs 3 passes, blocks above
  `INJECTION_THRESHOLD` (0.6), and fails open on provider errors; urgency comes only from the CSV.
  See `docs/BUSINESS_RULES.md`; no new work.
- **FR-017** (already implemented): `--now <ISO with offset>` freezes the clock through the injected
  `clock` provider; structured LLM output failures are diagnosed with `LlmOutputError` and thinking
  is disabled for guard and structured calls.
- **FR-018**: Prompts MUST NOT embed fixed example dates (such as 2024 or 2025) and MUST present
  `requested_date` consistently with `date_from`/`date_to`.

### Key Entities

- **DateCheck**: frozen verdict of a date validation (validity, error code, English reason, real
  weekday, nearest valid value).
- **Visit hours**: closed local window [`SLOT_DAILY_START_HOUR`, `SLOT_DAILY_END_HOUR`] in which a
  whole visit must fit.
- **Visit horizon**: `VISIT_HORIZON_DAYS` natural days from the reference day.
- **Rejection reply**: fixed deterministic message sent to a sender for rejected input.

## Success Criteria *(mandatory)*

- **SC-001**: 100% of intervals outside 09-19, in the past, beyond the horizon, or with a wrong
  weekday are rejected in deterministic unit tests, with the correct `DateErrorCode`.
- **SC-002**: No rejected date produces availability evidence, a proposal, or a terminal result.
- **SC-003**: Empty, oversized, and unknown-work-order inputs never reach an LLM or create a worker.
- **SC-004**: A tenant clarification answer is never processed on the handyman path (regression test).
- **SC-005**: Every rejection emits an `availability_rejected` trace event with the contract detail.
- **SC-006**: The full test suite passes with the frozen clock and no live API dependence.

## Assumptions

- The user decided that the presentation grid 09:00-19:00 is also the permitted visit window.
- `VISIT_HORIZON_DAYS` defaults to 7 natural days.
- Guard, `--now`, diagnostics, and limits settings are already implemented (FR-016, FR-017, FR-009 settings).
- Natural-language dates are validated deterministically. The LLM interpreter does not decide
  validity: it only extracts, in the mandatory `mentioned_dates` field, each mentioned date or time
  split into components; code always validates them (`validate_mentioned_date`,
  `first_mention_problem`) and a strict `validate_date` tool is offered to the model as a helper.
  If the year is not stated, the next future occurrence is used. Relative dates are validated only
  where exact. An interval outside 09:00-19:00 is rejected whole, never trimmed.
- The slot table is capped to the horizon (lookahead = horizon + 1 days, no longer 35). A window
  partly beyond the horizon shows only the slots inside it plus the limit sentence; a window fully
  beyond shows only the sentence and traces `slot_window_beyond_horizon`
  (`{actor: system, requested: [from, to], last_known}`).

## Open Decisions (user)

- **OD-001 (RESOLVED, user decision)**: The 7-day horizon is not extended. The system states how
  far it knows the agenda instead: es "Solo conozco la disponibilidad hasta el {weekday_es}
  {YYYY-MM-DD}. Indíqueme una fecha dentro de ese límite." / en "I only know the availability until
  {Weekday} {YYYY-MM-DD}. Please give me a date within that limit." The rejection of a date beyond
  the horizon (`too_far_ahead`) carries this limit (facts `last_known_date`, `last_known_weekday`)
  and the slot table is capped to the horizon as described in Assumptions.

## Round 2 (live verification follow-ups)

A live run against the real API (`integration_test/`, clock 2026-10-12 12:00 Europe/Madrid) found
12 further defects, tracked in `tasks.md` T026-T036: prose validator too strict and fallback
without table (1), "el viernes" not linked to the table (2), relative date read as whole-day
interval (3), bare hours not resolved by the 09-19 window (4), horizon off by one and "next week"
(5), `nearest_valid` not validated (6), invented past example years (7), empty intervals (8),
availability ignored in `tenant_alternatives` (9), handyman not told of a withdrawn proposal
(10), wrong weekday names (11) and missing `hold_released`/`proposal_withdrawn` trace events (12).
Each has a live scenario; resolved or pending status is recorded in `tasks.md`.

## Known Risks and Limitations

- The LLM sometimes returns empty intervals for valid input; `interpret_availability` retries up
  to 3 attempts (2 on broken JSON) and only then falls back to deterministic literal checks.
- The injection guard can produce false negatives (self-reported probability) and fails open on
  provider errors; downstream deterministic validation remains authoritative.
- Rejection replies exist only in Spanish and English templates; any other language gets the
  bilingual `<en> / <es>` form.
- Offers to the handyman may coincide before any hold exists, because `docs/BUSINESS_RULES.md` allows
  it ("A free or strict-higher-urgency-preemptible candidate may be asked of the handyman").
  Arbitration happens when the hold is created and confirmed appointments are never preempted
  (`tests/integration/test_competing_offers.py`). No two appointments overlap, but a Low order can
  receive the slot if it confirms before a higher-urgency one, a consequence of confirmed
  appointments being immutable. This is conforming behavior and a known risk, not a defect.
- Ruff reports 5 E501 line-length warnings (`application/workflow.py` x3,
  `prompts/interpret_availability.py` x2); the user decided not to fix them.
