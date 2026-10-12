# Feature Specification: Vague Date Request Handling with Deterministic Slot Table

**Feature Branch**: `005-vague-slot-suggestion`
**Created**: 2026-10-12
**Status**: Draft
**Input**: User description: "añadamos un nodo antes que compruebe si tiene una fecha o una petición, por ejemplo 'WO-002|tenant esta semana por la tarde, ¿qué días pueden ser?'; que ahí el agente tenga tools y pueda analizar y revisar el calendario de disponibilidad y entonces dar en una tabla de markdown (determinista, siempre la misma) los espacios que hay; y que otro LLM antes de que se devuelva compruebe si es posible ese horario; en caso de que no sea posible le manda feedback y no lo deja salir hasta que sea así; cuenta cuántas veces fue el reintento, en la 3era lo envías a otro estado que le diga 'puedes ser más específico', por ejemplo que ponga la próxima disponible. Recuerda revisar SpecKit para hacer el plan."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Vague date request triggers the slot-table node (Priority: P1)

When the tenant replies with a vague date expression or an open question instead of explicit
availability intervals (for example "esta semana por la tarde, ¿qué días pueden ser?" or "quiero
para mañana a las 2"), the negotiation workflow enters a new node placed **before** the strict
availability-extraction node. In this node the agent consults the shared agenda through tools,
derives the currently known open two-hour slots, and replies with a deterministic markdown table
of candidate spaces plus a request to pick one or supply explicit intervals.

**Why this priority**: This is the core new behavior; without it the tenant with a vague request
keeps receiving the generic "give me complete availability intervals" message that motivated this
feature.

**Independent Test**: Send `WO-002|tenant esta semana por la tarde que dias pueden ser?` to a
running order in the availability node; the reply must contain the deterministic markdown slot
table and must not be the generic complete-availability prompt.

**Acceptance Scenarios**:

1. **Given** an unfinished work order waiting for tenant availability, **When** the tenant sends a
   message containing a relative/vague date reference or an open scheduling question without any
   fully specified interval, **Then** the workflow classifies the message as a vague date request
   and enters the slot-suggestion node instead of asking again for complete intervals.
2. **Given** the slot-suggestion node, **When** it runs, **Then** the reply contains a markdown
   table with the same columns, ordering, and row format on every invocation (deterministic
   rendering), populated only from real shared-agenda evidence.
3. **Given** a tenant message that already contains at least one fully specified interval
   (explicit calendar date plus start/end times), **When** it is processed, **Then** the existing
   availability-extraction path runs unchanged and no slot table is produced.

---

### User Story 2 - Feasibility validation gate with bounded feedback retries (Priority: P1)

Before the slot-table reply is sent to the tenant, a separate validator pass checks the drafted
reply against the same agenda evidence: every slot listed must actually be open per the shared
agenda, the table must match the deterministic format, and no invented availability may appear.
If validation fails, the validator's feedback is returned to the composer and the reply is
regenerated; the loop repeats until validation passes. The number of composition attempts is
counted per tenant message.

**Why this priority**: The user explicitly asked for a pre-send validator LLM that blocks invalid
output and retries with feedback; it is inseparable from the table node for correctness.

**Independent Test**: Inject a forced validation failure in a test double; the composer must be
re-invoked with the validator feedback, and after the configured retry budget the deterministic
fallback path must be taken.

**Acceptance Scenarios**:

1. **Given** a drafted slot-table reply that lists a slot occupied in the shared agenda, **When**
   validation runs, **Then** the reply is not sent, and the composer receives feedback naming the
   invalid slot and regenerates.
2. **Given** a drafted reply that passes validation, **When** validation completes, **Then** the
   reply is sent to the tenant exactly once and no further composition occurs.
3. **Given** repeated validation failures, **When** the third composition attempt also fails
   validation, **Then** the workflow leaves the retry loop and enters the fallback state (User
   Story 3) instead of looping forever; the retry counter is recorded.

---

### User Story 3 - Third-retry fallback state with "be more specific" guidance (Priority: P2)

When the third composition attempt fails validation, the workflow transitions to a distinct
fallback state whose reply is fully deterministic (no LLM composition). The reply tells the tenant
to be more specific — for example to name the next available slot explicitly — and includes the
next open slot computed directly from agenda evidence, followed by the request for explicit
intervals. The order then continues the normal negotiation graph from that point.

**Why this priority**: Guarantees the tenant always receives a valid, actionable reply even when
LLM composition repeatedly fails; it is the safety net for the retry loop.

**Independent Test**: Force three consecutive validation failures; the emitted reply must be the
deterministic fallback text containing the next open slot derived from the agenda, and the
workflow must continue awaiting the tenant's next message in a consistent state.

**Acceptance Scenarios**:

1. **Given** the third composition attempt failed validation, **When** the fallback state runs,
   **Then** the tenant receives the deterministic "be more specific" reply naming the next open
   slot, in the tenant's recognized language.
2. **Given** the fallback reply was sent, **When** the tenant replies with explicit intervals or
   picks a listed slot, **Then** the normal negotiation flow continues (availability extraction /
   candidate inspection) with no state corruption.
3. **Given** the fallback reply was sent, **When** the tenant sends another vague message,
   **Then** the slot-suggestion node runs again with a fresh retry counter.

---

### User Story 4 - Slot classification feeds the existing clarification semantics (Priority: P3)

A tenant message that names a concrete relative date with an unambiguous time (for example
"mañana a las 2 de la tarde") is resolved via calendar tools into a concrete suggested interval
and confirmed with the tenant, reusing the existing relative-date confirmation behavior; only
messages that remain vague after tool-assisted analysis enter the slot-table path.

**Why this priority**: Improves precision of routing but the order still progresses without it via
the table; lower urgency than the node, gate, and fallback.

**Independent Test**: Send "mañana a las 2 de la tarde"; the reply must be a confirmation of the
resolved absolute interval, not the slot table and not the generic availability prompt.

**Acceptance Scenarios**:

1. **Given** a tenant message with a resolvable relative date and explicit time-of-day, **When**
   calendar tools resolve it unambiguously, **Then** the workflow asks the tenant to confirm the
   concrete interval (existing relative-date confirmation behavior).
2. **Given** a tenant message whose relative expression stays ambiguous after tool-assisted
   resolution (for example "mañana a las 2" without AM/PM), **When** routed, **Then** the
   slot-suggestion node handles it and the deterministic table includes the candidate
   interpretations' surrounding open slots.

### Edge Cases

- Tenant sends a vague request after the workflow has moved past availability (candidate
  selection, proposal, finalization): the message is handled per the current pending-question
  rules; the slot-table node must not resurrect a superseded node.
- The agenda contains no open slots at all in the look-ahead window: the table is emitted with
  zero rows (or an explicit "no open slots" line per the deterministic format) and the reply
  still asks for explicit intervals.
- All agenda evidence is unknown (fresh order, no handyman evidence yet): the table may only
  state what is known — e.g. confirmed appointments and holds as occupied — and must not present
  invented "free" handyman time as available.
- Validator and composer disagree repeatedly on the same content: capped by the retry budget;
  the third failure deterministically exits to the fallback state.
- The tenant mixes one explicit interval plus a vague question: the explicit interval is treated
  as availability evidence per existing rules; the vague part does not discard it.
- Language: the table and fallback reply are rendered in the tenant's recognized language for
  that work order, with the handyman always addressed in Spanish per existing binding rules.
- Human-timeout policy is untouched: `<NO RESPONSE>` handling and terminal semantics remain
  exactly as in `BUSINESS_RULES.md`; the retry loop is an internal composition loop within one
  inbound message, not a message retry policy.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The workflow MUST classify each inbound tenant message in the availability phase
  into: (a) contains at least one fully specified interval, (b) vague date request / open
  scheduling question, or (c) explicit-only decision, before running availability extraction.
- **FR-002**: For category (b), the workflow MUST enter a slot-suggestion node that consults the
  shared agenda (snapshot of confirmed appointments, tentative holds, and known availability
  evidence) through the existing scheduling authority interface before composing any reply.
- **FR-003**: The slot table MUST be rendered deterministically: fixed column set, fixed ordering
  (by UTC start, then stable slot ID), fixed row format, identical for the same agenda data and
  look-ahead window; the table generation must not depend on LLM free-form output.
- **FR-004**: The table MUST only contain slots derived from real shared-agenda evidence and MUST
  NOT invent availability, consent, dates, or handyman availability, per the Agreement and
  Scheduling Invariants of `BUSINESS_RULES.md`.
- **FR-005**: Every drafted slot-suggestion reply MUST pass a separate validation pass before
  being sent, checking: (1) each listed slot is open per the shared agenda, (2) the table matches
  the deterministic format, (3) no availability beyond known evidence is claimed, (4) the reply
  language matches the recognized tenant language.
- **FR-006**: On validation failure, the system MUST send the validator's feedback back to the
  composer and regenerate the reply; the reply MUST NOT be sent while invalid.
- **FR-007**: The system MUST count composition attempts per inbound tenant message; on the third
  failed attempt it MUST stop composing and enter the deterministic fallback state.
- **FR-008**: The fallback state MUST produce its reply without LLM composition: a deterministic
  message in the tenant's language telling the tenant to be more specific, naming the next open
  slot computed directly from agenda evidence, and requesting explicit availability intervals.
- **FR-009**: Both the slot-table node and the fallback state MUST leave the order in the tenant
  availability node's pending-question state so the normal negotiation graph continues unchanged
  on the next tenant message.
- **FR-010**: The retry loop and its outcome MUST be recorded as functional events in the run's
  JSONL trace (timestamp, work-order ID, event type, attempt count, and outcome), per the tracing
  rules of `BUSINESS_RULES.md`.
- **FR-011**: A tenant message with a relative date resolvable via calendar tools into a single
  concrete interval with explicit time-of-day MUST route to the existing relative-date
  confirmation path rather than the slot table (per Pending Policy approval for the reference
  clock in `BUSINESS_RULES.md`).
- **FR-012**: An "open" slot in the table MUST mean only "not occupied in the shared agenda" —
  i.e. a two-hour interval within the look-ahead window that does not overlap any confirmed
  appointment or tentative hold in the shared agenda. The table MUST NOT claim or imply handyman
  availability for those slots; a fixed disclaimer line in the deterministic format states that
  agenda-open slots do not guarantee the handyman is available.
- **FR-013**: The look-ahead window for the deterministic table MUST be the 7 local days starting
  from the reference day (the day of the reference time in the approved `LOCAL_TIMEZONE`), sliced
  into a fixed grid of consecutive two-hour slots from a fixed daily start hour to a fixed daily
  end hour.

### Key Entities *(include if feature involves data)*

- **Tenant message classification**: the routing verdict for an inbound tenant message in the
  availability phase (explicit intervals / vague date request / decision).
- **Slot table**: the deterministic markdown rendering of open two-hour slots derived from the
  shared agenda; columns, ordering, and format fixed by this feature's contract.
- **Validation verdict**: result of the pre-send validator pass on a drafted reply (valid /
  invalid with feedback).
- **Retry counter**: number of composition attempts for the current inbound tenant message;
  resets on each new tenant message; drives the third-attempt fallback transition.
- **Fallback state**: the deterministic reply-producing state entered after the third failed
  composition attempt; not a terminal status.
- **Workflow state**: extended with the classification verdict, retry counter, and the
  slot-suggestion node cursor; the tenant, shared handyman resource, appointments, holds, and
  existing availability evidence entities are unchanged.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any two runs with identical shared-agenda evidence and look-ahead window, the
  slot table is byte-identical (determinism).
- **SC-002**: 100% of slot-suggestion replies sent to the tenant have passed the validation
  gate; zero invalid replies are emitted.
- **SC-003**: The composition retry loop never exceeds 3 attempts; after the 3rd failed attempt
  the deterministic fallback reply is always emitted within the same inbound-message handling.
- **SC-004**: A tenant sending "esta semana por la tarde que dias pueden ser?" receives a reply
  containing the deterministic slot table (not the generic complete-availability prompt) in at
  least 95% of test conversations.
- **SC-005**: Existing negotiation outcomes (terminal statuses, agreement invariants, CSV/CLI
  contracts) are unchanged: full regression suite of Feature 004 passes without modification.

## Assumptions

- The existing scheduling authority snapshot (appointments, holds, availability evidence) is the
  only legitimate source for slot derivation; no external calendar service is introduced.
- LLM composition and validation use the already-approved external provider configuration;
  the validator is a separate invocation from the composer.
- The retry budget of 3 composition attempts is per inbound tenant message and is internal to
  reply production; it does not interact with the human-timeout (`<NO RESPONSE>`) policy.
- The tenant's recognized language for the work order is already available from Feature 003.
- Existing Feature 004 negotiation graph, states, and contracts remain in scope and are only
  extended, not replaced.
