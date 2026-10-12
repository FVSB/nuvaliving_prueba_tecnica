# Tasks: Deterministic Date, Role, and Input Validation Fixes

**Input**: `specs/006-validate-date-tool/` (spec.md, plan.md)
**Tests**: every task includes deterministic tests (fakes, frozen clock).
Format: `[ID] [P?] [Story] Description`. Waves: 0 (done) -> 1 (A, B1, C in parallel) -> 2 (B2) -> 3 (V).

## Wave 0: Already implemented

- [x] T001 `--now` frozen clock via `__main__.py`, `bootstrap.py`, `dependencies.py`, `NegotiationWorkflow(clock=...)`
- [x] T002 Prompt-injection guard (3 passes, 0.6 threshold, fail open) in `application/injection_guard.py` and graph node
- [x] T003 LLM output diagnostics (`LlmOutputError`) and thinking disabled in the guard
- [x] T004 Limit settings `visit_horizon_days` and `max_message_length` in `config.py`, `.env.example`

## Package A: Date validation (wave 1)

- [x] T005 [US1] Create `src/maintenance_agent/domain/date_validation.py` with `DateErrorCode`, `DateCheck`, `validate_interval`, `validate_date_text`; unit tests for each code (errors 3, 5, 6)
- [x] T006 [US1] Add `AvailabilityInterpretation.invalid_reason: DateCheck | None` in `application/conversation.py` and use the tool as safety net in the interpreter
- [x] T007 [US1] Disable `thinking` and avoid `max_tokens` exhaustion in compose, validator, interpreter, and language recognizer (error 2)
- [x] T008 [US1] Remove 2024/2025 examples and make `requested_date` coherent with `date_from/date_to` in `prompts/interpret_availability.py` (error 7)
- [x] T009 [US1] Emit `availability_rejected` trace detail per contract (error 4, with B2)

## Package B1: Roles, cancellation, decisions (wave 1)

- [x] T010 [US2] Dispatch clarification answers by role in `handle`, `_ask`, `_clarify` (error 8)
- [x] T011 [US2] Cancel/correct availability decisions in `domain/decisions.py` and decision branches (error 9)
- [x] T012 [US2] Attribute `<NO RESPONSE>` to the sending role (error 10)
- [x] T013 [US2] Handyman natural acceptance with restated date/time (error 14)

## Package C: Inbound input validation (wave 1)

- [x] T014 [US3] Reject unknown work order without creating a worker (error 11)
- [x] T015 [US3] Reject empty and over-`MAX_MESSAGE_LENGTH` bodies before any LLM (error 12)
- [x] T016 [US3] Fixed reply to the sender for rejected lines (error 13)

## Package E: Documentation (wave 1)

- [x] T017 Spec, plan, tasks, decision 006, `docs/BUSINESS_RULES.md`, `docs/configuration.md`, `docs/development.md`
- [x] T018 Fill TODO(E-final) markers once A, B1, C report exact texts and event names

## Package B2: Slots and validation in workflow (wave 2, after A and B1)

- [x] T019 [US1] Apply `validate_interval` in `_record_tenant_intervals` and `_handyman_availability` (errors 3, 4)
- [x] T020 [US4] Bind "el viernes" after the slot table to displayed slots in `_slot_suggestion` (error 15)
- [x] T021 [US4] Deterministic test for the same slot offered to two orders before a hold; fix only if reproduced (error 16). Outcome: conforming behavior per `docs/BUSINESS_RULES.md`; `tests/integration/test_competing_offers.py`, no code fix
- [x] T022 Run deterministic checks before the LLM validator in slot suggestion (FR-008)

## Package V: Verification (wave 3)

- [ ] T023 Full `uv run pytest` green; no live API dependence
- [ ] T024 Live smoke with `--now 2026-10-12T12:00:00+02:00` for 03:00, 2062, wrong weekday, WO-999, empty, 5000 chars
- [ ] T025 OD-001 already resolved by the user (horizon stays 7; the agent states how far it knows the agenda); docs aligned, pending final check

## Round 2: fixes after live verification with the real API (packages L, W, T)

Points as numbered in the round 2 briefing. Status is confirmed by the live scenarios in
`integration_test/` (see `integration_test/README.md`); a point stays pending while its
`known_issue` check still reports XFAIL.

- [ ] T026 (1) Relax the prose validator criterion; after exhausting attempts the fallback shows the deterministic table with a fixed localized text (L: validator, W: fallback)
- [ ] T027 (2) "el viernes"/"el 14" after the table links to the displayed slots first (`table_reply_linked`) (W)
- [ ] T028 (3, 4) A relative date without time is not a whole-day interval; bare hours resolve with `resolve_bare_hour` against 09-19 (L, W)
- [ ] T029 (5) Horizon off by one: Monday 2026-10-19 is included; "next week" shows what falls inside plus the limit sentence (W)
- [ ] T030 (6) `nearest_valid` goes through the same validations or is None (L)
- [ ] T031 (7, 11) Compose receives `today` and pre-formatted dates (`format_local_date`); no invented example dates or weekdays (L, W)
- [ ] T032 (8) Robust retry / deterministic rescue for empty intervals in valid messages (L)
- [ ] T033 (9) New tenant availability in `tenant_alternatives` is recorded (W)
- [ ] T034 (10) Handyman notified (fixed Spanish text) when the tenant withdraws a pending proposal; event `proposal_withdrawn` (W)
- [ ] T035 (12) Trace event `hold_released` (W)
- [x] T036 (T) Live scenarios added: `alternatives_new_availability_is_recorded`, `handyman_notified_when_proposal_withdrawn`, `weekday_names_are_correct_in_replies`, `hold_released_is_traced`, `recompose_has_no_stale_years`, `ambiguity_next_week_horizon_sentence`; `integration_test/README.md`
