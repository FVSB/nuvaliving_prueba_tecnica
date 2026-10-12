# Implementation Plan: Negotiate Visit Slots

**Branch**: `004-negotiate-visit-slots` | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)  
**Input**: Approved feature scope and policy decisions; see [Decision 005](../../docs/decisions/005-visit-negotiation.md)  
**Status**: Planning artifacts complete; tasks and cross-artifact analysis are separate follow-on steps.

## Branch Workflow

**Working branch**: `004-negotiate-visit-slots`, continuing on top of feature 003 as authorized  
**Integration branch**: `develop`  
**Deviation**: The approved feature 003 baseline has not merged to `develop`; Decision 005 records why feature 004 is stacked on it. Do not represent the branch as based on a newer `develop` than it is.

## Summary

Replace the current one-shot language/initial-message graph lifecycle with retained per-work-order negotiation. The tenant provides explicit intervals first; deterministic domain rules derive two-hour candidates and the shared agenda evaluates holds and priority. A common injected conversation handler receives participant messages and sends composed responses. Typed graph nodes interpret evidence, ask each role for confirmation of one immutable proposal, and commit only after both explicit acceptances and schedule revalidation. Exactly two terminal outcomes remain.

This is a proposed design for later implementation. The user's approval covers the feature specification and planning artifacts; it is not implementation approval or evidence that runtime behavior has changed.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: Existing LangGraph, Pydantic v2, dependency-injector, Anthropic integration; no new dependency expected  
**Storage**: Run-local state; in-memory shared schedule authority; existing JSONL traces  
**Testing**: pytest, pytest-asyncio, Ruff; meaningful domain, graph, coordinator, schedule-race and CLI-protocol tests are required by the spec and must be included in later tasks  
**Target Platform**: Docker CLI on Linux  
**Project Type**: Single-process asynchronous CLI application  
**Performance Goals**: Different work orders progress concurrently; one order processes inbound events sequentially  
**Constraints**: No new service, calendar, CSV field, setting, channel, relative-date policy, or timeout policy; do not hold schedule lock across model, participant, or transport waits  
**Scale/Scope**: Shared agenda, per-order graph state, participant language and availability, two-party explicit confirmation, two terminal outcomes

## Constitution Check

*Gate: passed for the planning scope; rechecked after the design below.*

- [x] `docs/BUSINESS_RULES.md`, `docs/TECHNICAL_ARCHITECTURE.md`, and the constitution were reviewed. Decision 005 is the approved exception/supersession record for the changes to language, initial candidate policy, hold transfer, and no-common-time handoff.
- [x] User approval covers the described feature specification and planning artifacts. Implementation, code edits, and verification are separate follow-on work.
- [x] The design remains a Docker CLI and adds no service or dependency.
- [x] Graph nodes, typed state, injected handler, schedule authority, trace details, and lifecycle changes are described below and in the contracts.
- [x] Work continues from the approved feature context on `004-negotiate-visit-slots`; repository history is stacked on feature 003 because required baseline work is not yet in `develop`. Decision 005 records this exception rather than claiming a fresh `develop` base.

## Repository Baseline

CodeGraph inspection reports the current `AsyncCoordinator._start` invokes the graph and writes its `outbound_message`, but discards returned graph state. `_consume` routes each message to a separate injected `inbound_node`, currently echo behavior, instead of resuming negotiation state. The current graph is `START -> recognize_language -> initialize_coordination -> END`, and initialization is fixed Spanish. `AsyncStdoutWriter.write` serializes a complete message block; it does not currently write terminal result frames. `TraceWriter.write` uses a lock to serialize JSONL appends. These facts guide the proposed integration; they do not describe the completed feature.

## Architecture and Data Flow

The CLI coordinator retains graph state keyed by work-order ID and sends each inbound event through a per-order queue. `application/conversation.py` defines injected `ConversationHandler`, `MessageInterpreter`, and `MessageComposer` ports. `infrastructure/cli_conversation.py` adapts the existing CLI reader/writer; `infrastructure/anthropic_conversation.py` implements typed interpretation and composition using the same startup-injected Anthropic client. Inbound events route to coordinator queues. Graph nodes never read stdin, compete on `readline`, or block their order worker waiting for a future participant message: the graph emits an outbound intent and pending question, yields, and a later queued inbound event resumes retained state. A final `compose_message` node is the only path to outbound participant text and chooses the stored recipient language.

The graph contains focused nodes for language recognition, incident introduction/tenant availability request, tenant evidence interpretation/candidate creation, handyman availability request and interpretation, proposal selection, role-bound confirmation handling, availability reversal resolution, no-common-time handoff, final proposal revalidation/commit, and terminal output. Participant yes/no replies are interpreted by a pure deterministic domain function; the Anthropic adapter extracts availability only and may request local calendar context when resolving relative weekdays. Ambiguous input cannot be coerced to yes or no. The exact `<NO RESPONSE>` terminal path bypasses confirmation handling because no consent is being requested or inferred.

Terminal outcomes use a closed `TerminalStatus(StrEnum)` domain type in `domain/negotiation.py`, with exactly `SCHEDULED = "scheduled"` and `REQUIRES_REVIEW = "requires_review"`. The per-order state keeps a nullable `terminal_status` until completion. Graph cursor and pending action are separate types, never extra terminal statuses. Output and trace serialize the exact enum values.

The schedule authority owns every shared agenda read and write behind one `asyncio.Lock`. It returns frozen detached snapshots, evaluates and mutates holds/preemption/commit atomically, and revalidates the relevant candidate, proposal and overlapping occupants before mutations. It checks all UTC interval starts, including handyman counterproposals not aligned to the initial candidate slices. A global schedule version change caused by an unrelated interval triggers reevaluation, not repeated rejection. No model, participant, or transport wait holds the lock. Cross-order preemption emits an internal versioned event to the displaced order's queue without acquiring another order's lock.

Commit atomically creates an immutable globally visible appointment, writes `terminal_status=SCHEDULED`, and sets `finalization_pending=true`. `close_review` and scheduled commit are mutually exclusive under the schedule authority. Confirmation delivery to tenant and handyman is a sequential idempotent continuation; a committed appointment cannot be preempted, and delayed `<NO RESPONSE>` cannot alter its status. The exact scheduled terminal frame is emitted after both confirmations succeed. A failed delivery retains the scheduled decision and pending finalization without emitting a premature frame or freeing the time. Terminal output adds a typed writer for the existing documented frame format.

## Proposed Source Structure

```text
src/maintenance_agent/
├── domain/
│   ├── negotiation.py                 # Candidate, proposal, consent, TerminalStatus, ReviewReason
│   └── scheduling.py                  # Pure overlap, eligibility and urgency rules
├── application/
│   ├── conversation.py                # Handler, interpreter, and composer ports
│   ├── scheduling.py                  # Shared ScheduleAuthority port and result types
│   └── coordinator.py                 # Per-order queues and retained graph state
├── infrastructure/
│   ├── in_memory_schedule.py          # Locked authority and immutable snapshots
│   ├── cli_transport.py               # Existing writer plus typed terminal frame writer
│   ├── cli_conversation.py            # CLI adapter for common handler port
│   └── anthropic_conversation.py      # Typed interpretation/composition with startup client
├── prompts/
│   ├── interpret_availability.py      # Typed evidence extraction prompt
│   ├── decisions.py                   # Deterministic explicit yes/no interpretation
│   └── compose_message.py             # Language-aware complete message prompt
└── agents/scheduling/
    ├── graph.py                       # Wiring and routes only
    ├── state.py                       # Typed reducer state and version context
    └── nodes/                         # One focused module per significant node

tests/
├── unit/                              # Domain intervals, priorities, typed decisions
├── integration/                       # Graph lifecycle, handler binding, schedule races
└── acceptance/                        # Existing CLI frames and end-to-end terminal behavior
```

Names above are planning targets; later tasks may refine exact module boundaries while preserving the described contracts and architecture.

## Implementation Sequence

1. Add immutable domain records and pure rules for tenant interval union/splitting, contained explicit handyman counterproposals, overlap across arbitrary starts, candidate order, eligibility, consent identity, hold transfer eligibility, terminal invariants, and the closed two-member `TerminalStatus` enum.
2. Define injected `ConversationHandler`, `MessageInterpreter`, `MessageComposer`, and `ScheduleAuthority` ports with typed results. Keep network/model/CLI I/O outside domain policy.
3. Implement the locked in-memory authority. Serialize every read and write, return immutable detached snapshots, and make hold transfer, review closure, and commit atomic. Revalidate the candidate, proposal and overlapping occupants immediately before mutation; unrelated schedule changes cause reevaluation against the current snapshot.
4. Extend typed graph state and implement focused nodes. Pre-filter tenant candidates against shared occupancy and priority before querying the handyman; do not ask about equal/higher-held or confirmed slots. Accept a handyman counterproposal only when it is fully contained in the tenant's original interval union, then pre-filter it and ask the tenant to confirm the exact slot; it is not consent. Route all outbound content through language-aware composition. Ask tenant to confirm the current proposal, then ask handyman unless that exact version already has valid explicit handyman acceptance. Keep each role's unique outstanding question and bind interpretation to its pending action and relevant versions.
5. Change coordinator lifecycle to retain returned graph state through inbound calls, serialize a work-order queue, route inbound events through the handler adapter, and handle cross-order schedule events without nested locks. Replace the current independent inbound echo path; graph invocations yield between messages rather than blocking for human input.
6. Implement idempotent post-commit confirmations and typed terminal writer. Atomic commit records `SCHEDULED` plus pending finalization; a send failure retains both and emits no premature frame. Exact incoming no-response closes an unfinished order as `REQUIRES_REVIEW`; it cannot change an already committed order. Model review explanation as structured `ReviewReason` (never a terminal status) and serialize deterministic evidence into one safe line.
7. Add deterministic JSONL events using existing trace facilities, covering node transitions and availability/preemption/actor/version evidence while excluding credentials and model private reasoning.
8. Add the Mermaid source at `docs/graphs/004-visit-negotiation-flow.mmd` during implementation and make it match the compiled graph. Render a PNG when available; keep planned graph documentation clearly separate until runtime exists.
9. Run the meaningful checks required by the later task plan. Report fake-model, CLI, Docker, and real-provider verification separately; do not report planned coverage as run.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Current coordinator discards graph state | Retain state per order and test multiple inbound invocations against one state. |
| Two orders race for overlapping time | One shared authority serializes all access and atomically evaluates/mutates. |
| Stale or duplicate messages target newer state | Bind unique outstanding question and versions; re-ask full slot when unversioned stdin makes delay ambiguous. |
| Preemption strands a displaced participant | Atomic transfer records affected orders, emits internal queued events, and notifies each tenant in their language. |
| Confirmation send fails after commit | Appointment stays committed; idempotent finalization retries delivery, and `scheduled` waits for both successful sends. |
| Model invents availability or interprets ambiguity as yes | Typed evidence validation and deterministic domain checks; ambiguous confirmation remains clarification-required. |
| DST edge changes duration | Do not create a new policy; clarify ambiguous local time and defer a cross-transition two-hour visit to authorized review. |
| Diagram or trace implies implementation prematurely | Publish runtime graph diagram and example trace only with implementation; planning artifacts label them proposed. |

## Complexity Tracking

No new service or dependency is proposed. The schedule authority and retained per-order state are necessary to enforce the single shared agenda and resume conversations. The apparent repository-branch deviation is documented as an approved continuation exception in Decision 005.
