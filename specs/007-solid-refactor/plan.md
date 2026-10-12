# Implementation Plan: SOLID Refactor and Duplication Removal

**Branch**: `007-solid-refactor` | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/007-solid-refactor/spec.md`

## Summary

Remove the duplicated helpers found in `src/maintenance_agent/` and restructure the largest modules
so each has one responsibility, applying SOLID. The work is behaviour-preserving: existing tests
stay green, trace names and tenant-visible text do not change. Phases run in order; each phase ends
with a green test run and its own commit.

## Technical Context

**Language/Version**: Python 3.12 (`pyproject.toml`, `uv`)
**Primary Dependencies**: `anthropic`, `langgraph`, `pydantic`, `dependency-injector`
**Storage**: in-memory schedule + JSONL trace (unchanged)
**Testing**: `pytest` + `pytest-asyncio` under `tests/unit`, `tests/integration`, `tests/acceptance`
**Target Platform**: Linux Docker CLI (unchanged)
**Project Type**: CLI agent application, layered as `domain/` → `application/` → `infrastructure/`
**Constraints**: no behaviour change; no new LLM call; no new trace event; no new runtime dependency
without `uv add`
**Scale/Scope**: ~7 new modules, 2 large modules split, 1 protocol split, ~6 duplicate helpers removed

## Constitution Check

- [x] No business rule change (`docs/BUSINESS_RULES.md` unaffected).
- [x] Layer direction kept: `domain` imports nothing from `application` or `infrastructure`;
  `application` depends on protocols it owns; `infrastructure` implements them.
- [x] Each phase is independently revertible.
- [ ] Language-detection unification (US5) pending approval.
- [ ] `mypy`/`pyright` dependency (open question) pending approval.

## Phases

### Phase 0 — Baseline and characterization (no production code change)

1. Record `uv run pytest` result (baseline count and time).
2. Record a baseline live run: `uv run python integration_test/run.py --all -j 3` (API cost; run
   once, with approval).
3. For `workflow.py`, `anthropic_conversation.py`, `in_memory_schedule.py` and `coordinator.py`,
   add characterization tests that pin current outputs for the public methods that will move.
4. Confirm the Ruff plan: `uv run poe auto-fix` only; manual Ruff fixes need approval.

Exit: baseline recorded, characterization tests green.

### Phase 1 — Remove duplicated deterministic helpers (DRY, lowest risk)

| Change | From | To |
|---|---|---|
| Fold text | `decisions._fold` + inline in `interpret_explicit_decision` | `domain/text.py: fold()` |
| Interval overlap | `application/slot_table._overlaps` | import `domain/scheduling.overlaps` |
| Weekday names | `slot_table._WEEKDAYS`, `_WEEKDAYS_ES`; `date_validation._WEEKDAYS`, `_weekday_name` | `domain/weekdays.py` (EN, ES, index helpers) |
| First text block | `_first_text` (unused) + inline in `_text` and `anthropic_language_recognizer` | `infrastructure/anthropic_gateway.py: first_text()` (used after Phase 2) |

Exit: grep check (SC-002) passes for each helper; tests green.

### Phase 2 — LLM gateway (DIP, SRP)

1. `application/llm.py`: `LlmGateway` Protocol with `complete_text(prompt, max_tokens)` and
   `complete_structured(prompt, schema, model_type, label, max_tokens)`.
2. `infrastructure/anthropic_gateway.py`: the only module calling `messages.create`. Owns
   `thinking={"type": "disabled"}`, `output_config`, `first_text()` and `structured_output()`.
3. `AnthropicInjectionClassifier`, `AnthropicLanguageRecognizer`, `AnthropicConversationHandler`
   receive `LlmGateway` in their constructors. The private `_structured_output` import is removed.
4. Unit tests use a fake `LlmGateway`; existing tests keep patching at the boundary where they do now
   (the fake client) until they are migrated in the same phase.

Exit: `grep -rn "messages.create(" src/` returns one match. Tests green.

### Phase 3 — Split `anthropic_conversation.py` (SRP, ISP)

Target layout under `infrastructure/conversation/`:

| Module | Content |
|---|---|
| `availability.py` | `interpret_availability`, `_normalized` corrections (`_without_unrequested_whole_days`, `_with_explicit_range_rescued`, `_with_bare_hour_resolved`) |
| `date_rules.py` | literal ranges, bare-hour resolution, `_validate_date_*` |
| `tools.py` | calendar, resolve-range, validate-date and read-skill tool definitions |
| `slot_reply.py` | `compose_slot_reply`, `translate` |
| `language.py` | `detect_language` (until Phase 6 decision) |
| `handler.py` | `AnthropicConversationHandler`: thin facade implementing the segregated protocols |

Exit: `anthropic_conversation.py` removed or reduced to re-exports; tests green.

### Phase 4 — Split `workflow.py` (SRP, OCP)

Sequencing: the flow handlers (step 2) should depend on the segregated protocols from Phase 5, so
Phase 5 lands first when moving flows. Step 1 (presenter) can start earlier.

1. Extract `application/availability_presenter.py` with `AvailabilityPresenter(timezone)`:
   `interval_text`, `moment_text`, `format_windows`, `slot_text`. Pure functions, unit-tested.
2. Extract flow handlers under `application/flows/`:
   `TenantAvailabilityFlow`, `HandymanAvailabilityFlow`, `ProposalFlow`, `CorrectionFlow`,
   `CancellationFlow`, `FinalizationFlow`. Each receives only the ports it uses.
3. Replace the `if` chain in `NegotiationWorkflow.handle` with a dispatch table keyed by
   `(state, message class)`.
4. Move one flow at a time; run tests after each move.

Exit: `workflow.py` under 400 lines or justified; each flow file has one responsibility.

### Phase 5 — Segregate `ScheduleAuthority` (ISP, DIP)

| Protocol | Methods |
|---|---|
| `AvailabilityReader` | `snapshot`, `inspect_candidates`, `known_eligible_candidates` |
| `HoldManager` | `acquire_or_transfer_hold`, `release_hold`, `close_review` |
| `AppointmentWriter` | `commit_appointment`, `apply_availability_change`, `terminal_result` |

`InMemoryScheduleAuthority` implements all three. Each flow depends on the protocols it calls.
`ScheduleAuthority` is kept as a type alias for the composition root only, or removed.

Exit: each consumer's signature references only the protocols it uses; tests green.

### Phase 6 — Language detection (needs approval, User Story 5)

Only if approved in `research.md`:
- One `LanguageRecognizer` port used by the graph node and by the composer.
- Remove `ConversationHandler.detect_language` and its prompt, or keep it as a delegating method.
- Expect a change in LLM call count for messages that currently call both paths. Record the change
  in the spec before implementing.

If not approved: skip this phase; both paths stay and the decision is recorded.

### Phase 7 — One composition root (DIP)

1. Move all object construction from `dependencies.py` into `bootstrap.py`.
2. Remove `injection_guard = providers.Object(None)` placeholders by passing real objects or
   removing the provider.
3. Delete `dependencies.py` if empty, or keep it as providers only.

Exit: `grep -rn "Container(" src/` shows one composition root.

### Phase 8 — Final validation

1. `uv run pytest` full.
2. `uv run poe auto-fix`.
3. Live run `integration_test/run.py --all -j 3` once, compared with the Phase 0 baseline
   (no new `FAIL`; `XPASS` reviewed).
4. Re-read `integration_test/README.md` trace names against the new code (no renames).

## Project Structure (after refactor, additions only)

```text
src/maintenance_agent/
├── domain/
│   ├── text.py                 # fold()            [new, Phase 1]
│   └── weekdays.py             # EN/ES names       [new, Phase 1]
├── application/
│   ├── llm.py                  # LlmGateway port   [new, Phase 2]
│   ├── availability_presenter.py  [new, Phase 4]
│   ├── flows/                  # per-flow handlers [new, Phase 4]
│   └── scheduling.py           # protocols split   [Phase 5]
└── infrastructure/
    ├── anthropic_gateway.py    # only messages.create [new, Phase 2]
    └── conversation/           # split of anthropic_conversation.py [new, Phase 3]
```

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Silent behaviour change in `workflow.py` (1,663 lines) | Characterization tests in Phase 0; one flow moved per commit |
| Private helpers imported by tests break | Update imports only; no assertion edits (SC-001) |
| Trace output drift | Compare JSONL shape in characterization tests; no event renames |
| Live API cost | Baseline and final live run only; at most 2 runs per scenario (README) |
| Scope creep into features | Phases 1–5 and 7 are refactor-only; Phase 6 gated by approval |
| Ruff noise | `poe auto-fix` only; manual fixes need approval |

## Complexity Tracking

| Item | Why it is needed | Simpler alternative rejected because |
|---|---|---|
| Protocols split into 3 (Phase 5) | ISP is a stated goal and `ScheduleAuthority` has 6 methods | A single protocol keeps coupling; grep showed consumers use disjoint subsets |
| Flow dispatch table (Phase 4) | OCP for new message classes | Keeping the `if` chain leaves the 1,663-line file in place |
| `SLOT-` label and `stable_slot_id` kept separate | They are different identifiers with different consumers (`outbound_guard`) | Merging would change visible labels or leak-guard behaviour |
