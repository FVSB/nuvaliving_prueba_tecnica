# Feature Specification: SOLID Refactor and Duplication Removal (maintenance_agent)

**Feature Branch**: `007-solid-refactor` (no git branch created; work continues on the current branch)
**Created**: 2026-10-12
**Status**: Draft
**Input**: User request: remove repeated and near-identical code in `src/maintenance_agent/` and
restructure the architecture applying SOLID principles, without changing observable behaviour.

## Scope

In scope: `src/maintenance_agent/` only.

Out of scope: `tests/` (only characterization tests are added where needed), `integration_test/`
(live harness), new business rules, new LLM prompts, new trace event names, changes to
`docs/BUSINESS_RULES.md`.

## Problem

Audit of `src/maintenance_agent/` (about 6,700 lines) found:

- `application/workflow.py` (1,663 lines) mixes tenant, handyman, proposal, correction,
  cancellation, formatting and tracing in one class (SRP, OCP).
- `infrastructure/anthropic_conversation.py` (930 lines) mixes interpretation, composition,
  language detection, date rules, tool schemas and the HTTP client (SRP, DIP).
- `ScheduleAuthority` exposes six methods; consumers use a subset (ISP).
- Six direct `messages.create(...)` calls across three adapters, with no shared abstraction (DIP).
- Two composition roots: `dependencies.Container` and `bootstrap.build_container` (DIP).
- Duplicated code:
  - `_fold()` in `domain/decisions.py` and the same NFKD/casefold/combining-strip inline in
    `interpret_explicit_decision` (same file).
  - `_overlaps()` in `application/slot_table.py` identical to `domain/scheduling.overlaps()`.
  - Weekday names defined in `slot_table.py` (EN tuple, ES tuple), `date_validation.py` (EN+ES dict)
    and `calendar.day_name`.
  - "first text block of a response" extraction repeated in three places, with a helper
    (`_first_text`) that is not used by two of them.
- Two language-detection paths: `ConversationHandler.detect_language` and
  `AnthropicLanguageRecognizer`, with two prompts.

## Behaviour Contract (must not change)

- Every existing test in `tests/` passes unchanged, except tests that import a moved private helper
  (imports only may change).
- Trace event names, field names and order are unchanged (`TraceWriter` output contract).
- Tenant- and handyman-visible messages are byte-identical for the same input and the same
  deterministic (non-LLM) code path.
- Slot identifiers are unchanged: the `SLOT-…` labels and the 16-hex `stable_slot_id` values keep
  their current formats. They are two different identifiers (`SLOT-` is the presentation label;
  `stable_slot_id` is the internal id checked by `outbound_guard`). They are not merged.
- LLM call count and arguments per message are unchanged, except the language-detection path if
  User Story 3 is accepted.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Remove duplicated helpers with no behaviour change (Priority: P1)

A maintainer finds one implementation for each deterministic helper (folding, interval overlap,
weekday names, text extraction) and every caller imports it from the layer that owns it.

**Independent Test**: Grep for each removed helper name returns only the single definition and its
imports; `uv run pytest` is green with no assertion changes.

**Acceptance Scenarios**:

1. **Given** `interpret_explicit_decision` and `_fold` both normalise text, **When** the refactor is
   done, **Then** only `domain/text.fold()` performs NFKD normalisation in `src/`.
2. **Given** `slot_table._overlaps` and `domain/scheduling.overlaps`, **When** the refactor is done,
   **Then** one definition remains and `slot_table` imports it.
3. **Given** weekday names in three places, **When** the refactor is done, **Then** one module
   `domain/weekdays.py` owns EN and ES names and the others import it.

### User Story 2 - Single LLM gateway (Priority: P1)

All Anthropic calls go through one `LlmGateway` port implemented by one adapter. Consumers depend
on the port, not on the SDK client.

**Independent Test**: Unit tests can substitute `LlmGateway` with a fake; no test needs to patch
`messages.create` directly to exercise the handlers.

**Acceptance Scenarios**:

1. **Given** the injection classifier, language recognizer and conversation handler, **When** they
   call the model, **Then** they call `LlmGateway.complete_text` or `complete_structured`.
2. **Given** `_structured_output` is used by two modules, **When** the refactor is done, **Then** it
   lives in the gateway module and is imported publicly, not as a private name across modules.

### User Story 3 - Split large modules by responsibility (Priority: P2)

`anthropic_conversation.py` is split into interpretation, composition, date rules, tool schemas and
a thin facade. `workflow.py` is split into a presenter and per-flow handlers, with
`NegotiationWorkflow` as a thin orchestrator.

**Independent Test**: No module in `src/maintenance_agent/` exceeds 400 lines (target, not a hard
gate), and each new module has one reason to change.

**Acceptance Scenarios**:

1. **Given** a new inbound message class, **When** a developer adds it, **Then** they add one flow
   handler and register it; `NegotiationWorkflow` does not gain another `if` branch.
2. **Given** the workflow formats an interval for a tenant, **When** the formatter is called,
   **Then** the call goes through `AvailabilityPresenter`, which is a pure, testable object.

### User Story 4 - Segregate interfaces and inject one composition root (Priority: P2)

Consumers depend on the narrowest protocol they use. `ScheduleAuthority` is split into
`AvailabilityReader`, `HoldManager` and `AppointmentWriter`. `ConversationHandler` is split into
interpretation, composition, translation and language detection protocols. `bootstrap.py` is the
only composition root.

**Independent Test**: Each consumer's constructor type-annotation references only the protocols it
calls (checked by reading the signatures and by `mypy` or `pyright` if the project already uses one).

**Acceptance Scenarios**:

1. **Given** `SafeFallbackConversationHandler`, **When** it is used anywhere the primary handler is
   used, **Then** the same contract tests pass for both (Liskov).
2. **Given** `dependencies.Container` and `bootstrap.build_container`, **When** the refactor is
   done, **Then** only `bootstrap.py` wires objects and `dependencies.py` no longer exists or only
   declares providers.

### User Story 5 - One language-detection path (Priority: P3, needs approval)

The conversation handler's `detect_language` and `AnthropicLanguageRecognizer` are unified behind
`LanguageRecognizer`.

**Why P3 and gated**: it changes the number of LLM calls and the prompt used for the same decision.
It is implemented only after explicit approval recorded in `research.md`.

## Requirements

- **FR-001**: Each deterministic helper listed in the Problem section has exactly one definition in
  `src/`.
- **FR-002**: All Anthropic SDK calls are made from one adapter module.
- **FR-003**: `ScheduleAuthority` is replaced by three protocols; the in-memory implementation
  satisfies all three.
- **FR-004**: `NegotiationWorkflow` dispatches to flow handlers; it contains no per-message-class
  business branch beyond the dispatch table.
- **FR-005**: `bootstrap.py` is the only module that constructs production objects.
- **FR-006**: Before any move, characterization tests exist for each module being split.
- **FR-007**: Each phase ends with a green `uv run pytest` and a single commit.
- **FR-008**: `uv run poe auto-fix` may be used freely. Manual Ruff fixes require explicit user
  approval before work starts (`AGENTS.md`).

## Success Criteria

- **SC-001**: `uv run pytest` passes after every phase with no assertion edits.
- **SC-002**: Grep-based check: each removed duplicate has exactly one definition in `src/`.
- **SC-003**: No change to trace event names or to tenant-visible text for deterministic paths.
- **SC-004**: `workflow.py` and `anthropic_conversation.py` are each below 400 lines, or each
  remaining line count has a written justification in `research.md`.
- **SC-005**: One full live run of `integration_test/run.py --all -j 3` shows no new `FAIL` against
  the baseline captured in phase 0.

## Assumptions

- Python 3.12, `uv`, `pytest` and `pytest-asyncio` are already in use.
- `integration_test/` is the live harness and is run only at the end (it costs API calls).
- Specify (`.specify/`) remains authoritative for this feature (see `CLAUDE.md`).

## Open Questions

- Language detection unification (User Story 5): approve or keep both paths.
- Whether to add `mypy` or `pyright` to validate the protocol segregation (dependency change: must be
  recorded through `uv add --dev` per `CLAUDE.md`).
