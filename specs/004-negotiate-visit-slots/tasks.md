# Tasks: Negotiate Visit Slots

**Input**: Design documents in `specs/004-negotiate-visit-slots/` (spec, plan, research, data model, contracts, quickstart)
**Prerequisites**: Approved `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/negotiation.md`, and `quickstart.md`

**Tests**: Automated coverage is explicitly required by FR-024 and the plan. The test tasks below cover the domain rules, graph continuation and typed decisions, concurrent schedule authority, stale and duplicate responses, terminal idempotency and recovery, structured review reasons, and the existing CLI framing.

**Organization**: Tasks are grouped by user story after shared domain, ports, and agenda foundations. Implement one sequentially executing model; `[P]` only marks independent files that can be prepared without unfinished implementation dependencies.

## Format: `- [ ] T### [P?] [US#?] Description with file path`

## Phase 1: Setup

**Purpose**: Prepare feature-specific test and source locations using the existing Python package and dependencies. No new dependency or setting is required.

- [ ] T001 Add focused negotiation test modules under `tests/unit/`, `tests/integration/`, and `tests/acceptance/` following the repository's existing pytest layout
- [ ] T002 Add the scheduling graph node package structure under `src/maintenance_agent/agents/scheduling/nodes/` for focused negotiation nodes

---

## Phase 2: Foundational Types, Ports, and Shared Agenda

**Purpose**: Establish shared contracts that every user story relies on before story implementation.

- [ ] T003 [P] Define immutable negotiation records, participant roles, pending actions, proposal/decision bindings, and the closed two-value `TerminalStatus` in `src/maintenance_agent/domain/negotiation.py`
- [ ] T004 [P] Define UTC interval normalization, merge overlapping tenant evidence windows before initial candidate slicing, stable candidate IDs/deduplication, semi-open overlap, candidate ordering, common-window intersection, and urgency comparison rules in `src/maintenance_agent/domain/scheduling.py`
- [ ] T005 Define typed handler, interpreter, composer, and schedule authority ports and results in `src/maintenance_agent/application/conversation.py` and `src/maintenance_agent/application/scheduling.py`
- [ ] T006 Define retained per-order graph state, nullable terminal status, pending question/version context, and distinct graph cursor types in `src/maintenance_agent/agents/scheduling/state.py`
- [ ] T007 Implement the single-lock in-memory schedule authority, detached immutable snapshots, and atomic hold transfer, availability update, review closure, release, and appointment commit in `src/maintenance_agent/infrastructure/in_memory_schedule.py`
- [ ] T008 Add unit coverage for interval boundaries, merged-window candidate slicing and stable deduplication, distinct overlapping candidates from different source starts, two-hour common-window intersections, urgency comparison, immutable snapshots, atomic multi-hold transfer, conflicting holds, and confirmed-visit protection in `tests/unit/test_negotiation_domain.py` and `tests/unit/test_schedule_authority.py`
- [ ] T009 Add authority concurrency tests proving serialized reads/writes, conflict-free concurrent acquisition, mutually exclusive review/commit, and no lock held across external waits in `tests/integration/test_schedule_authority.py`
- [ ] T010 Test the two-member terminal enum, null-until-closed invariant, and structured `ReviewReason` codes/evidence fields in `tests/unit/test_negotiation_domain.py`

**Checkpoint**: Domain records, explicit I/O boundaries, retained graph state, and serialized shared agenda are available for story work.

---

## Phase 3: User Story 1 — Tenant Language and Availability Introduction (Priority: P1)

**Goal**: Start each work order with a grounded introduction in the tenant's recognized language and ask for all explicit availability before producing tenant-derived candidates. Handyman communication remains Spanish.

**Independent Test**: Start orders with Spanish, English, another supported language, and undetermined language; verify grounded language-appropriate introductions, per-order language isolation, explicit-interval requests, UTC normalization, and non-overlapping full two-hour candidates beginning at each stated start.

- [ ] T011 [P] [US1] Add language, grounded-introduction, per-order isolation, and tenant-first candidate acceptance tests in `tests/integration/test_negotiation_language_and_availability.py`
- [ ] T012 [P] [US1] Add typed availability extraction and language-aware composition prompts in `src/maintenance_agent/prompts/interpret_availability.py` and `src/maintenance_agent/prompts/compose_message.py`
- [ ] T013 [US1] Implement the common Anthropic conversation adapter using the existing injected startup client, with structured availability extraction, optional local-calendar tool use, and language-aware composition in `src/maintenance_agent/infrastructure/anthropic_conversation.py`
- [ ] T014 [US1] Implement tenant-language-scoped introduction, neutral multilingual clarification, and first all-availability request nodes in `src/maintenance_agent/agents/scheduling/nodes/recognize_language.py` and `src/maintenance_agent/agents/scheduling/nodes/request_tenant_availability.py`
- [ ] T015 [US1] Implement validated tenant availability interpretation, deterministic UTC two-hour candidate creation, and participant-time display through the existing injected local-timezone setting (default `Europe/Madrid`) in `src/maintenance_agent/agents/scheduling/nodes/interpret_tenant_availability.py` and `src/maintenance_agent/domain/scheduling.py`
- [ ] T016 [US1] Route all outbound intents through recipient-language composition and the existing CLI writer in `src/maintenance_agent/agents/scheduling/nodes/compose_message.py` and `src/maintenance_agent/infrastructure/cli_conversation.py`
- [ ] T017 [US1] Wire the language and tenant-availability path into the compiled graph and make US1 runnable through the injected handler, per-order coordinator state, and CLI bootstrap in `src/maintenance_agent/agents/scheduling/graph.py`, `src/maintenance_agent/application/coordinator.py`, `src/maintenance_agent/dependencies.py`, and `src/maintenance_agent/bootstrap.py`
- [ ] T018 [US1] Verify recognized and unknown languages, grounded facts, absolute-interval clarification, timezone display/UTC comparison, merged tenant windows, and no invented dates or evidence; exercise start and resumed turns with deterministic provider/handler fakes through the CLI adapter (graph nodes never await stdin) in `tests/integration/test_negotiation_language_and_availability.py` and `tests/acceptance/test_negotiation_cli.py`

**Checkpoint**: A tenant can provide explicit windows and receive candidate requests in their scoped language without any handyman availability or consent being inferred.

---

## Phase 4: User Story 2 — Shared Agenda Preemption (Priority: P1)

**Goal**: Ask the handyman only about agenda-eligible tenant candidates, protect equal/higher holds and appointments, and atomically transfer all overlapping lower-urgency tentative holds only after the requester selects the candidate.

**Independent Test**: Verify pre-filtering at every urgency level, strict-higher transfers of all overlapping holds, denial by equal/higher holds or confirmed appointments, half-open adjacency, displaced-tenant notification, and deterministic earliest-known replacement selection.

- [ ] T019 [P] [US2] Add tests for agenda pre-filtering, all urgency comparisons, selected-candidate transfer, denied transfers, displaced notifications, and deterministic replacement ordering in `tests/integration/test_agenda_preemption.py`
- [ ] T020 [US2] Implement agenda candidate inspection and free/preemptible/blocked result types in `src/maintenance_agent/application/scheduling.py` and `src/maintenance_agent/infrastructure/in_memory_schedule.py`
- [ ] T021 [US2] Implement tenant candidate pre-filtering and tenant alternative requests for equal/higher holds and appointments in `src/maintenance_agent/agents/scheduling/nodes/filter_agenda_candidates.py` and `src/maintenance_agent/agents/scheduling/nodes/request_tenant_alternatives.py`
- [ ] T022 [US2] Implement Spanish handyman availability requests restricted to free or strict-higher-preemptible candidates, plus typed evidence validation in `src/maintenance_agent/agents/scheduling/nodes/request_handyman_availability.py` and `src/maintenance_agent/agents/scheduling/nodes/interpret_handyman_availability.py`
- [ ] T023 [US2] Implement requester-selected candidate authorization followed by atomic all-overlap hold transfer and release in `src/maintenance_agent/agents/scheduling/nodes/select_candidate.py` and `src/maintenance_agent/infrastructure/in_memory_schedule.py`
- [ ] T024 [US2] Queue displaced-work-order events and notify each affected tenant in their scoped language with the earliest already-known eligible interval or a renewed availability request in `src/maintenance_agent/application/coordinator.py` and `src/maintenance_agent/agents/scheduling/nodes/handle_displaced_hold.py`
- [ ] T025 [US2] Verify full two-hour explicit availability, blocked-candidate exclusion from handyman questions, occupied candidate choices, atomic transfer races, and adjacent interval eligibility; for tenant 09:00–13:00 (initial candidates 09:00–11:00 and 11:00–13:00) and handyman counter-availability 10:00–12:00 verify 10:00–12:00 is created from the common source-window intersection, a tenant yes continues to handyman confirmation without implying consent or causing false review, and overlapping candidates from distinct starts remain available for agenda adjudication in `tests/integration/test_agenda_preemption.py`

**Checkpoint**: One shared agenda remains conflict-free while candidate ownership and priority transfers are deterministic and auditable.

---

## Phase 5: User Story 3 — Mutual Yes/No and Commit (Priority: P1)

**Goal**: Obtain a separate explicit yes/no from each participant for one immutable proposal version, then atomically revalidate and commit before sending idempotent confirmations and the scheduled frame.

**Independent Test**: A scheduled result is possible only when current tenant and handyman yes decisions match the same proposal and the agenda revalidation succeeds; no, ambiguity, stale/duplicate responses, or failed finalization never create a false frame or free a committed slot.

- [ ] T026 [P] [US3] Add graph tests for retained state across inbound invocations, question binding, typed yes/no/clarification, matching proposal consent, and stale or duplicate messages in `tests/integration/test_negotiation_consent.py`
- [ ] T027 [P] [US3] Add acceptance tests for exact terminal frame bytes/lines and send-failure recovery in `tests/acceptance/test_negotiation_terminal_output.py`
- [ ] T028 [US3] Implement and test deterministic explicit yes/no interpretation; ambiguous or availability-only replies remain unresolved in `src/maintenance_agent/domain/decisions.py` and `tests/unit/test_negotiation_domain.py`
- [ ] T029 [US3] Implement immutable proposal creation, separate role-specific confirmation questions, and validation of role/question/action/proposal/workflow/schedule context in `src/maintenance_agent/agents/scheduling/nodes/propose_candidate.py` and `src/maintenance_agent/agents/scheduling/nodes/interpret_confirmation.py`
- [ ] T030 [US3] Implement final relevant-interval revalidation and atomic appointment commit with both acceptances, `SCHEDULED`, and `finalization_pending=true` in `src/maintenance_agent/infrastructure/in_memory_schedule.py` and `src/maintenance_agent/agents/scheduling/nodes/commit_appointment.py`
- [ ] T031 [US3] Implement sequential idempotent tenant/handyman confirmations and pending-finalization continuation in `src/maintenance_agent/agents/scheduling/nodes/finalize_appointment.py` and `src/maintenance_agent/application/coordinator.py`
- [ ] T032 [US3] Add typed two-line terminal frame writing while preserving existing message framing in `src/maintenance_agent/infrastructure/cli_transport.py`
- [ ] T033 [US3] Verify explicit matching consent, no-as-rejection, ambiguity clarification, stale/duplicate isolation, unrelated schedule-version reevaluation, immutable commit, idempotent finalization continuation after delivery failure without an automatic retry policy, and exact scheduled frame in `tests/integration/test_negotiation_consent.py` and `tests/acceptance/test_negotiation_terminal_output.py`

**Checkpoint**: The appointment cannot be scheduled from availability alone, and post-commit delivery can resume without releasing or duplicating the appointment.

---

## Phase 6: User Story 4 — Availability Reversal (Priority: P2)

**Goal**: Suspend disputed intervals when a participant contradicts prior availability, ask that sender to confirm old or new evidence, and invalidate affected proposal and consent state when the change is confirmed.

**Independent Test**: Reverse tenant and handyman availability in both directions; ensure old evidence remains recorded while disputed, no affected proposal can commit, confirmed updates invalidate only relevant offer/acceptance evidence, and stale/duplicate confirmations are inert.

- [ ] T034 [P] [US4] Add reversal, dispute suspension, stale confirmation, and affected-work-order invalidation tests in `tests/integration/test_availability_reversals.py`
- [ ] T035 [US4] Implement contradiction detection, retained prior evidence, sender-bound old/new confirmation questions, and affected proposal/consent invalidation in `src/maintenance_agent/agents/scheduling/nodes/resolve_availability_change.py` and `src/maintenance_agent/domain/negotiation.py`
- [ ] T036 [US4] Implement shared handyman availability change propagation as versioned internal events through each affected work-order queue in `src/maintenance_agent/application/coordinator.py` and `src/maintenance_agent/infrastructure/in_memory_schedule.py`
- [ ] T037 [US4] Verify tenant and handyman reversal flows, disputed interval exclusion, confirmation application, and duplicate/stale no-ops in `tests/integration/test_availability_reversals.py`

**Checkpoint**: A disputed availability value cannot support a proposal or commit, and shared handyman changes reach affected orders through their ordered queues.

---

## Phase 7: User Story 5 — No Response and Human Handoff (Priority: P1)

**Goal**: Close unfinished orders on the exact `<NO RESPONSE>` body, or offer human scheduling only when known complete evidence proves there is no eligible shared interval.

**Independent Test**: Exact silence signals from either role produce one `requires_review`; strings with extra characters or whitespace do not. Partial evidence and provider errors keep the order active. Complete empty evidence asks the tenant; yes closes with evidence, no requests new availability, ambiguity is clarified, and delayed signals cannot alter scheduled orders.

- [ ] T038 [P] [US5] Add exact and near-match no-response tests for both roles, unfinished versus committed orders, and transport/provider errors in `tests/integration/test_no_response_and_handoff.py`
- [ ] T039 [P] [US5] Add structured review-reason and deterministic one-line evidence serialization tests in `tests/unit/test_review_reason.py`
- [ ] T040 [US5] Implement no-common assessment only after complete tenant and handyman evidence; implement schedule-only no-eligible assessment after tenant alternatives/all-availability requests are exhausted and every requested candidate is agenda-blocked, then ask the tenant yes/no/clarification about human scheduling in `src/maintenance_agent/agents/scheduling/nodes/assess_eligibility.py` and `src/maintenance_agent/agents/scheduling/nodes/request_human_scheduling.py`
- [ ] T041 [US5] Implement atomic unfinished-order review closure for exact inbound `<NO RESPONSE>` and structured `ReviewReason` capture in `src/maintenance_agent/application/coordinator.py` and `src/maintenance_agent/infrastructure/in_memory_schedule.py`
- [ ] T042 [US5] Implement deterministic safe English `REASON:` serialization with escaped source line breaks and the exact `requires_review` terminal frame in `src/maintenance_agent/domain/negotiation.py` and `src/maintenance_agent/infrastructure/cli_transport.py`
- [ ] T043 [US5] Verify exact signal matching, no retries, complete no-common evidence, schedule-proven no-eligible evidence after alternatives are exhausted even when handyman availability is unknown, no false impossibility while free tenant candidates remain, human handoff choices, review/commit race, delayed post-commit no-response, and exact two-line review frame in `tests/integration/test_no_response_and_handoff.py` and `tests/acceptance/test_negotiation_terminal_output.py`

**Checkpoint**: Every review outcome has one permitted reason code and evidence, while provider failures and incomplete evidence never masquerade as silence or impossibility.

---

## Phase 8: Polish and Cross-Cutting Concerns

**Purpose**: Complete lifecycle wiring, run-local observability, graph documentation, and the approved feature verification scenarios.

- [ ] T044 Complete lifecycle wiring across all story paths: route full inbound bodies through the single CLI receiver and injected `ConversationHandler`, enqueue by work order, retain graph state across invocations, serialize each order's events, and allow independent orders to progress concurrently in `src/maintenance_agent/infrastructure/cli_conversation.py`, `src/maintenance_agent/application/coordinator.py`, and `src/maintenance_agent/bootstrap.py`
- [ ] T045 Complete compiled graph routing for all five stories, invoking focused nodes and yielding after each outbound question so later inbound events resume retained state without worker-owned stdin reads in `src/maintenance_agent/agents/scheduling/graph.py`
- [ ] T046 Instrument graph nodes and coordinator decisions with deterministic JSONL evidence for availability, actor, holds/transfers, and relevant versions, using the existing `TraceWriter` format and credential/private-reasoning redaction in `src/maintenance_agent/agents/scheduling/graph.py` and `src/maintenance_agent/application/coordinator.py`
- [ ] T047 Add the runtime Mermaid flow diagram matching the compiled negotiation graph in `docs/graphs/004-visit-negotiation-flow.mmd`, and render `docs/graphs/004-visit-negotiation-flow.png` only when a local renderer is already available (report renderer unavailability without installing tools)
- [ ] T048 Add end-to-end CLI acceptance coverage for existing inbound/outbound framing, unchanged CSV input, single terminal outcome, and isolated work orders in `tests/acceptance/test_negotiation_cli.py`
- [ ] T049 Validate all documented scenarios and required checks from `specs/004-negotiate-visit-slots/quickstart.md` and repository commands in `tests/acceptance/` (pytest and Ruff; report Docker and real-provider checks separately when unavailable)
- [ ] T050 After a complete deterministic fake-provider CLI run, capture a sanitized representative run-local event sequence in `docs/examples/004-visit-negotiation-events.jsonl`; derive it from actual runtime output, redact sensitive values, and do not fabricate events or claim unrun verification

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No feature dependencies; use the existing package, dependency set, and test conventions.
- **Foundational (Phase 2)**: Depends on setup and blocks all stories. Complete domain records, ports, typed state, schedule authority, and their core tests before story work.
- **User Stories (Phases 3–7)**: Depend on the foundation. Execute sequentially with one model; each phase has its own independent test criteria. US2 uses candidate/evidence concepts from US1. US3 uses eligible candidates and holds from US1/US2. US4 invalidates state created by US1–US3. US5 closes or redirects paths from all active stories.
- **Polish (Phase 8)**: Depends on all five independently runnable story paths; it completes lifecycle wiring and verifies integration, trace, protocol, and documentation together.

### User Story Dependencies

- **US1**: Starts after Phase 2; creates tenant language, explicit intervals, and candidates.
- **US2**: Starts after US1; consumes tenant candidates and shares the foundational schedule authority.
- **US3**: Starts after US2; consumes eligible availability and selected candidates for proposal/consent/commit.
- **US4**: Starts after US3; resolves changes to evidence and invalidates affected proposals and acceptance state.
- **US5**: Starts after US1 and the foundational authority; integrates with the active workflows from US2–US4 and their terminal transitions.

### Execution Strategy

Use one sequential model run: complete Setup, then the blocking foundation, then US1 through US5 in the order above, and finish with lifecycle wiring/polish. Within a phase, a `[P]` test or prompt file may be prepared independently, but implementation tasks remain ordered behind their actual dependencies. No multi-agent execution is needed.

### Coverage Map

- **FR-001, FR-021**: T003, T006–T010, T030–T033, T041–T043.
- **FR-002–FR-005, FR-020**: T011–T018.
- **FR-006–FR-009 (including UTC/local presentation and half-open interval behavior)**: T004, T007–T009, T015, T018–T025.
- **FR-010–FR-011**: T026–T033.
- **FR-012**: T034–T037.
- **FR-013–FR-014**: T038–T043.
- **FR-015–FR-017, FR-019**: T005–T007, T026–T033, T044–T045, T048.
- **FR-018**: T046, T050.
- **FR-022–FR-023**: T039, T042–T043, T027, T032.
- **FR-024 and SC-001–SC-007**: T008–T009, T018, T025, T033, T037, T043, T048–T050.

## Implementation Strategy

Deliver US1 as the first demonstrable increment after the foundation: it introduces scoped language handling and grounded tenant availability collection through the injected CLI adapter and retained per-order coordinator. Add US2 agenda eligibility and preemption, then US3 consent and atomic scheduling, followed by US4 reversals and US5 handoff/silence. The final phase completes integration across story paths and checks the exact protocol and trace behavior. Report automated, fake-provider, Docker, and real-provider verification separately; planned coverage is not a claim that a check has run.
