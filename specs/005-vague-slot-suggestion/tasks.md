# Tasks: Vague Date Request Handling with Deterministic Slot Table

**Input**: Design documents from `specs/005-vague-slot-suggestion/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/slot-table.md

**Tests**: Developer-approved: every task includes tests (unit/integration/acceptance) with
deterministic Anthropic fakes, per the constitution-required tests note in the template.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US4)

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Add `MessageClass`, `OpenSlot`, `SlotGridSpec`, and `SlotTable` value types plus
  `GraphCursor.SLOT_SUGGESTION` and `PendingAction.SLOT_SUGGESTION`/`SLOT_FALLBACK` in
  `src/maintenance_agent/domain/negotiation.py` and `src/maintenance_agent/application/scheduling.py`
  per data-model.md
- [x] T002 [P] Add slot grid settings (lookahead 7 days, daily 09:00-19:00, slot 2h) to the
  approved startup settings and composition root wiring per plan.md (no reload, injected once)

## Phase 2: Foundational (Blocking Prerequisites)

- [x] T003 Implement deterministic open-slot derivation + `SlotTable.render_markdown()` (fixed
  columns, ordering by UTC start then slot ID, zero-row line, disclaimer) in
  `src/maintenance_agent/application/scheduling.py` per contracts/slot-table.md, with unit tests
  for byte-determinism in `tests/unit/test_slot_table.py`
- [x] T004 [P] Add classification prompt returning `MessageClass` (explicit intervals / vague
  date request / decision) as an extended field of `AvailabilityInterpretation` in
  `src/maintenance_agent/prompts/interpret_availability.py` and
  `src/maintenance_agent/application/conversation.py`, with fakes in tests updated

## Phase 3: User Story 1 - Vague request triggers slot-suggestion node

- [x] T005 [US1] Route classification in `_tenant_availability` in
  `src/maintenance_agent/application/workflow.py`: explicit intervals keep existing branches,
  vague date request enters the slot-suggestion node, decision/unclassified keeps the existing
  clarification branch; unit tests in `tests/unit/test_workflow_classification.py`
- [x] T006 [US1] Implement the slot-suggestion node: snapshot the agenda, derive the slot table,
  compose the reply (LLM prose intro/closing, table injected verbatim), pending question returns
  to tenant availability, in `src/maintenance_agent/application/workflow.py`; unit tests with a
  fake composer in `tests/unit/test_slot_suggestion_node.py`
- [x] T007 [US1] Extend `AnthropicConversationHandler` with the slot-reply composer and validator
  calls plus prompts in `src/maintenance_agent/infrastructure/anthropic_conversation.py` and
  `src/maintenance_agent/prompts/slot_reply.py`; integration tests with deterministic fakes in
  `tests/integration/test_slot_reply_anthropic.py`
- [x] T008 [US1] Acceptance test: `WO-002|tenant esta semana por la tarde que dias pueden ser?`
  replies with the deterministic table (not the generic availability prompt) in
  `tests/acceptance/test_vague_date_request.py`

## Phase 4: User Story 2 - Validation gate with bounded feedback retries

- [x] T009 [US2] Implement the validation gate in the slot-suggestion node: deterministic
  pre-checks (table byte match, slot openness recomputation) + LLM validator verdict, feedback
  loop capped at 3 composition attempts, counter reset per inbound message, in
  `src/maintenance_agent/application/workflow.py` and a `ValidationVerdict` type in
  `src/maintenance_agent/application/conversation.py`; unit tests with a flaky fake in
  `tests/unit/test_slot_validation_gate.py`
- [x] T010 [US2] Add `slot_suggestion_attempt` and `slot_suggestion_feedback` JSONL trace events
  in `src/maintenance_agent/infrastructure/trace_writer.py`; unit tests assert timestamp,
  work-order ID, event type, attempt number, and feedback detail

## Phase 5: User Story 3 - Third-retry deterministic fallback state

- [x] T011 [US3] Implement the deterministic fallback reply (localized template: be more
  specific + next open slot + explicit-interval ask, no LLM) and the transition on the 3rd failed
  attempt, in `src/maintenance_agent/application/workflow.py` with language templates; unit tests
  in `tests/unit/test_slot_fallback.py`
- [x] T012 [US3] Add `slot_fallback_emitted` trace event in
  `src/maintenance_agent/infrastructure/trace_writer.py` with next slot ID/interval detail; unit
  tests included
- [x] T013 [US3] Acceptance tests in `tests/acceptance/test_slot_fallback_flow.py`: three forced
  validation failures emit the fallback reply, order stays non-terminal, next tenant message
  resumes the normal graph

## Phase 6: User Story 4 - Relative date routing precision

- [x] T014 [US4] Route unambiguous relative date + explicit time-of-day (e.g. "mañana a las 2 de
  la tarde") to the existing relative-date confirmation path, and ambiguous ones ("mañana a las
  2") to the slot-suggestion node, via calendar-tool resolution in the classification prompt;
  unit tests in `tests/unit/test_relative_date_routing.py`

## Phase 7: Polish & Cross-Cutting

- [x] T015 Run the full Feature 004 regression suite unmodified (`uv run pytest`) and fix any
  deviation; record results
- [x] T016 [P] Update docs (`docs/configuration.md` for new settings) and spec checklist; verify
  trace events against `contracts/slot-table.md` section 6 in
  `tests/integration/test_slot_traces.py`

## Dependencies

- US1 (T005-T008) depends on T003, T004; US2 (T009-T010) depends on T006, T007; US3 (T011-T013)
  depends on T009; US4 (T014) depends on T005; polish depends on all.
- Parallel: T001/T002; T003/T004; T011/T012 after T009.
- MVP: US1 alone delivers the table reply for vague requests.
