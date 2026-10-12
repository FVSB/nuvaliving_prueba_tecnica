# Implementation Plan: Vague Date Request Handling with Deterministic Slot Table

**Branch**: `005-vague-slot-suggestion` | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/005-vague-slot-suggestion/spec.md`

## Summary

Add a slot-suggestion node in front of the existing strict tenant-availability extraction: tenant
messages in the availability phase are first classified (explicit intervals / vague date request /
decision). Vague requests enter a node that snapshots the shared agenda, derives a deterministic
markdown table of agenda-open two-hour slots over a 7-day look-ahead grid (never claiming handyman
availability), composes the tenant reply with an LLM around that fixed table, and passes every
drafted reply through a separate LLM validator before sending. Invalid drafts regenerate with the
validator's feedback, capped at 3 composition attempts; the third failure transitions to a
deterministic, non-LLM fallback reply that tells the tenant to be more specific and names the next
open slot. Retry outcomes are traced to the run's JSONL.

## Technical Context

**Language/Version**: Python 3.12 (`pyproject.toml`, `uv`)
**Primary Dependencies**: `anthropic` (composer + validator via existing handler), `langgraph`
(coordinator), `pydantic` (typed outputs)
**Storage**: in-memory shared agenda (`InMemoryScheduleAuthority`) + JSONL trace writer
(`/app/traces`); no new storage
**Testing**: `pytest` + `pytest-asyncio` under `tests/unit`, `tests/integration`, `tests/acceptance`
**Target Platform**: Linux Docker CLI process (unchanged delivery contract)
**Project Type**: CLI agent application
**Performance Goals**: bounded LLM usage — at most 1 classification + 3 compositions + 3
validations per inbound tenant message
**Constraints**: no invented availability (`docs/BUSINESS_RULES.md`); deterministic table rendering;
retry loop never blocks the event loop or exceeds the 3-attempt budget
**Scale/Scope**: 1 new graph node, 1 fallback state, ~4 new prompts/tools additions, plus tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] `docs/BUSINESS_RULES.md` and `docs/TECHNICAL_ARCHITECTURE.md` were read and no authority conflict
  exists. ("Open slot" = not occupied in the shared agenda only; disclaimer that this does not
  imply handyman availability; no invented grid semantics beyond the approved 7-day window —
  flagged as a policy decision for developer sign-off in `research.md`.)
- [x] Developer approval, files, preview, risks, alternatives, and validation are recorded
  (approval granted conversationally for spec + plan; each implementation change will be
  pre-approved per Principle II).
- [x] The design is a Docker CLI and adds no unapproved service or business policy.
- [x] Nodes, typed state, injected dependencies, traces, and changed graph topology are documented
  (data-model.md, contracts/slot-table.md).
- [x] The work starts from the current feature branch `005-vague-slot-suggestion` (repo bootstrap
  predates a `develop` branch; recorded as an accepted deviation, see research.md).

## Branch Workflow

**Working Branch**: `005-vague-slot-suggestion`
**Integration Branch**: `develop` (not yet present; integration target is the repo default branch
until a `develop` branch exists)
**Merge Gate**: full `pytest` suite green, spec acceptance scenarios covered, trace events
verified, spec checklist complete

## Project Structure

### Documentation (this feature)

```text
specs/005-vague-slot-suggestion/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── slot-table.md    # Deterministic table + fallback reply contract
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/maintenance_agent/
├── agents/scheduling/
│   ├── graph.py               # add SLOT_SUGGESTION routing (extended)
│   ├── nodes/                 # new classify + slot-suggestion + fallback nodes
│   └── state.py               # retry counter + classification verdict fields (extended)
├── application/
│   ├── conversation.py        # AvailabilityInterpretation extended or new classification port
│   ├── slot_table.py          # agenda-open slot derivation (deterministic, application layer)
│   └── workflow.py            # _tenant_availability front-node integration (extended)
├── domain/
│   └── negotiation.py         # GraphCursor/PendingAction additions (extended)
├── infrastructure/
│   ├── anthropic_conversation.py   # classifier + composer + validator calls (extended)
│   └── in_memory_schedule.py       # snapshot-based open-slot query support (extended)
└── prompts/                   # new: classify_availability_intent.py, slot_reply.py,
                               # validate_slot_reply.py

tests/
├── unit/            # classification routing, table determinism, retry budget, fallback text
├── integration/     # node wiring, validator feedback loop with test doubles
└── acceptance/      # spec scenarios incl. "esta semana por la tarde" conversation
```

**Structure Decision**: single-project layout already established by Features 001-004; this
feature only extends `src/maintenance_agent` and `tests` in place. No new top-level directories.

## Complexity Tracking

> No constitution violations requiring justification. The 7-day fixed two-hour grid is a narrow,
  documented policy decision recorded in `research.md` and approved in the spec (FR-013); it does
  not contradict the 004 rule against inventing a *scheduling* grid because the grid is
  presentation-only for suggestions, never candidate or consent evidence.
