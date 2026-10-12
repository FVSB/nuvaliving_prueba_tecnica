# Tasks: SOLID Refactor and Duplication Removal

**Input**: `specs/007-solid-refactor/plan.md` and `spec.md`
**Rule**: each phase ends with a green `uv run pytest`. No assertion edits. One commit per phase.
Manual Ruff fixes are forbidden without approval (`AGENTS.md`); `uv run poe auto-fix` is allowed.

## Phase 0 — Baseline and characterization

- [ ] T001 Record `uv run pytest` baseline (count, duration) in `specs/007-solid-refactor/research.md`
- [ ] T002 Record a live baseline `uv run python integration_test/run.py --all -j 3` (needs approval: API cost)
- [ ] T003 [P] Characterization tests for `workflow.py` public entry points in `tests/unit/test_refactor_characterization_workflow.py`
- [ ] T004 [P] Characterization tests for `anthropic_conversation.py` pure helpers in `tests/unit/test_refactor_characterization_conversation.py`
- [ ] T005 [P] Characterization tests for `in_memory_schedule.py` in `tests/unit/test_refactor_characterization_schedule.py`
- [ ] T006 Confirm the Ruff plan with the user before any manual fix

## Phase 1 — Duplicated deterministic helpers (US1)

- [ ] T010 Create `src/maintenance_agent/domain/text.py` with `fold()`
- [ ] T011 Replace `_fold` and inline folding in `src/maintenance_agent/domain/decisions.py` with `fold()`
- [ ] T012 Remove `_overlaps` from `src/maintenance_agent/application/slot_table.py`; import `overlaps` from `domain/scheduling.py`
- [ ] T013 Create `src/maintenance_agent/domain/weekdays.py` (EN and ES names, index helpers)
- [ ] T014 Replace `_WEEKDAYS`, `_WEEKDAYS_ES` in `application/slot_table.py` with `domain/weekdays.py`
- [ ] T015 Replace `_WEEKDAYS` dict and `_weekday_name` in `domain/date_validation.py` with `domain/weekdays.py`
- [ ] T016 Grep check: each removed helper has one definition in `src/` (SC-002)

## Phase 2 — LLM gateway (US2)

- [ ] T020 Create `src/maintenance_agent/application/llm.py` with the `LlmGateway` Protocol
- [ ] T021 Create `src/maintenance_agent/infrastructure/anthropic_gateway.py` with `complete_text`, `complete_structured`, `first_text`, `structured_output`
- [ ] T022 Inject `LlmGateway` into `infrastructure/anthropic_injection_classifier.py`
- [ ] T023 Inject `LlmGateway` into `infrastructure/anthropic_language_recognizer.py`
- [ ] T024 Inject `LlmGateway` into `infrastructure/anthropic_conversation.py`
- [ ] T025 Remove the cross-module import of `_structured_output`
- [ ] T026 Grep check: `messages.create(` appears once in `src/`

## Phase 3 — Split `anthropic_conversation.py` (US3, ISP)

- [ ] T030 Create `infrastructure/conversation/availability.py` (interpretation and corrections)
- [ ] T031 Create `infrastructure/conversation/date_rules.py`
- [ ] T032 Create `infrastructure/conversation/tools.py`
- [ ] T033 Create `infrastructure/conversation/slot_reply.py` (compose and translate)
- [ ] T034 Create `infrastructure/conversation/language.py`
- [ ] T035 Reduce `AnthropicConversationHandler` to a facade in `infrastructure/conversation/handler.py`
- [ ] T036 Remove or re-export from `infrastructure/anthropic_conversation.py`

## Phase 4 — Split `workflow.py` (US3, OCP)

- [ ] T040 Create `application/availability_presenter.py` (`interval_text`, `moment_text`, `format_windows`, `slot_text`)
- [ ] T041 Replace presenter call sites in `workflow.py`
- [ ] T042 Create `application/flows/tenant_availability.py`
- [ ] T043 Create `application/flows/handyman_availability.py`
- [ ] T044 Create `application/flows/proposal.py`
- [ ] T045 Create `application/flows/correction.py`
- [ ] T046 Create `application/flows/cancellation.py`
- [ ] T047 Create `application/flows/finalization.py`
- [ ] T048 Replace the `if` chain in `NegotiationWorkflow.handle` with a dispatch table
- [ ] T049 Check `workflow.py` size against SC-004

## Phase 5 — Segregate `ScheduleAuthority` (US4, ISP)

- [ ] T050 Define `AvailabilityReader`, `HoldManager`, `AppointmentWriter` in `application/scheduling.py`
- [ ] T051 Make `infrastructure/in_memory_schedule.py` implement all three
- [ ] T052 Narrow each consumer's constructor type to the protocols it calls
- [ ] T053 Remove or alias `ScheduleAuthority`

## Phase 6 — Language detection (US5, needs approval)

- [ ] T060 Get explicit approval in `research.md`; skip this phase if not approved
- [ ] T061 Unify behind `LanguageRecognizer`; remove duplicate path and prompt
- [ ] T062 Record the LLM call count change in `spec.md` before merging

## Phase 7 — One composition root (US4, DIP)

- [ ] T070 Move construction from `dependencies.py` into `bootstrap.py`
- [ ] T071 Replace `injection_guard` placeholder `Object(None)`
- [ ] T072 Delete `dependencies.py` if empty
- [ ] T073 Grep check: one composition root in `src/`

## Phase 8 — Final validation

- [ ] T080 `uv run pytest` full run
- [ ] T081 `uv run poe auto-fix`
- [ ] T082 Live run `integration_test/run.py --all -j 3`, compared with T002 (needs approval)
- [ ] T083 Check trace event names in `integration_test/README.md` against the new code

## Dependencies

- Phase 0 blocks everything.
- Phase 1 blocks Phase 2 (`first_text` moves in Phase 2).
- Phase 2 blocks Phase 3.
- Phase 5 should land before Phase 4's flows depend on the narrowed protocols (T042-T047).
- Phase 6 is optional; Phase 7 can run after Phase 5.
