# Feature Specification: Negotiate Visit Slots

**Feature Branch**: `004-negotiate-visit-slots`  
**Created**: 2026-10-12  
**Status**: Ready for implementation handoff; policy decisions recorded in [Decision 005](../../docs/decisions/005-visit-negotiation.md)  
**Input**: Coordinate each work order in its tenant's recognized language, negotiate a feasible two-hour visit against one shared handyman agenda, and schedule only after tenant and handyman explicitly accept the same current proposal.

## User Scenarios & Testing

### User Story 1 — Start a clear, language-appropriate conversation (Priority: P1)

The coordinator introduces the incident in the tenant's recognized language, then asks the tenant to provide all availability as explicit intervals. The handyman is always addressed in Spanish. Language is remembered per `(work_order_id, role)`; no tenant identity is inferred across orders. An unrecognized tenant language is met with a neutral multilingual language question.

**Why this priority**: The tenant supplies the initial time evidence, and both participants must understand the negotiation.

**Independent Test**: Start orders with Spanish, English, another recognized language, and undetermined language; check the introductory and availability request messages, recipient language, and isolation between orders.

**Acceptance Scenarios**:
1. **Given** a recognized tenant language, **When** coordination starts, **Then** the tenant receives a cordial incident summary grounded in CSV facts and a request for all availability as explicit intervals.
2. **Given** tenant intervals overlap, **When** initial candidates are created, **Then** the system merges the requested interval union before slicing it into consecutive two-hour blocks, deduplicates equivalent candidates, and does not create overlapping initial candidates.
3. **Given** tenant language is undetermined, **When** communication is needed, **Then** the system asks a neutral multilingual clarification and does not guess.
4. **Given** multiple work orders, **When** a language is recognized, **Then** it is stored per order and role; handyman messages remain Spanish.

### User Story 2 — Find shared time while protecting the agenda (Priority: P1)

After tenant intervals are known, the coordinator asks the handyman about those candidate intervals. A candidate is schedulable only where both parties' explicit availability overlaps for a full two hours and the shared agenda permits it. A higher-urgency tenant-requested block can atomically take over tentative lower-urgency holds. Existing confirmed appointments cannot be displaced.

**Why this priority**: The shared agenda must remain conflict-free while candidates are negotiated.

**Independent Test**: Cover partial and complete intervals, overlaps, adjacent blocks, competing holds at every urgency level, and a confirmed appointment; verify deterministic eligibility and outcomes.

**Acceptance Scenarios**:
1. **Given** the tenant has supplied intervals, **When** handyman availability is requested, **Then** the question is limited to tenant-derived two-hour candidates.
2. **Given** the tenant's explicit window is 09:00–13:00 and the initial candidates are 09:00–11:00 and 11:00–13:00, **When** the handyman counter-proposes 10:00–12:00, **Then** that full interval is accepted as a candidate because it lies within the original tenant window, is checked against every overlapping agenda interval, and the tenant is asked to confirm that exact slot; the system does not conclude there is no common time merely because the counterproposal differs from the initial slices.
3. **Given** known tenant and handyman availability has no common eligible interval or the tenant's full requested set is exhausted by known agenda blockers, **When** the result is assessed, **Then** the tenant is asked whether they want human scheduling.
4. **Given** a tenant requests a block held by lower-urgency tentative proposals, **When** eligibility is evaluated, **Then** all overlapping lower-urgency holds are transferred atomically and each displaced tenant is told the old slot is unavailable.
5. **Given** an overlapping hold of equal or higher urgency or a confirmed appointment, **When** transfer is attempted, **Then** it is denied; the requesting tenant is asked for another candidate or all availability.
6. **Given** two intervals meet at an endpoint, **When** conflict is checked, **Then** both can be held because intervals are semi-open `[start, end)`.

### User Story 3 — Reach explicit agreement and close once (Priority: P1)

The system presents a concrete proposal and obtains an explicit yes from the tenant, then an explicit yes from the handyman, for the same immutable proposal ID/version. A prior explicit handyman acceptance can be reused only when it matches that exact current version. Availability does not count as acceptance. Only after both consents and a final agenda revalidation does the system commit the appointment, send confirmations to both, and produce the single `scheduled` result.

**Why this priority**: Mutual consent is the binding condition for scheduling.

**Independent Test**: Exercise yes/no, ambiguous, stale, duplicate and changed proposal responses; prove a scheduled result requires matching current consent from both roles.

**Acceptance Scenarios**:
1. **Given** availability is known, **When** no explicit confirmation has been received, **Then** the visit is not scheduled.
2. **Given** either participant says no, **When** the answer is interpreted, **Then** the proposal is not accepted and negotiation requests alternatives.
3. **Given** an ambiguous answer, **When** interpreted, **Then** it remains clarification-required and is not coerced into yes or no.
4. **Given** both roles explicitly accept the current proposal version, **When** finalization revalidates the agenda, **Then** the appointment is committed, both receive confirmations, and one scheduled result is emitted.
5. **Given** an old or duplicate answer arrives, **When** it is processed, **Then** it cannot mutate a newer proposal or terminal order.
6. **Given** exactly one proposal or slot is on the table, **When** the participant gives a short natural acceptance such as "ok, me gusta", "me parece bien" or "sounds good", **Then** it counts as an explicit yes for that single offer.
7. **Given** several slots are on the table, **When** the participant gives only a loose acceptance such as "ok me gusta", **Then** it is not a yes for any slot and the system asks which one they accept.
8. **Given** a short acceptance carries a condition, a negation, a change or a date/time (for example "ok pero a las 5" or "si pero no"), **When** it is interpreted, **Then** it is not a yes and remains clarification-required or is handled as availability.

### User Story 4 — Resolve changes to availability (Priority: P2)

Availability evidence remains separate by participant. When either participant contradicts a previously stated value, the system asks whether the old or new value is correct. The old value remains recorded, but the disputed interval is suspended from proposals and finalization until the sender confirms. A confirmed change invalidates affected proposals and acceptance evidence.

**Why this priority**: Reversals must not silently leave an unsafe or obsolete offer in place.

**Independent Test**: Apply available/unavailable reversals from tenant and handyman, resolve them, and check suspension, invalidation, stale replies, and audit history.

**Acceptance Scenarios**:
1. **Given** a participant reverses known availability, **When** the message is received, **Then** the old value is retained, the interval is disputed and suspended, and the participant is asked to confirm old or new.
2. **Given** the sender confirms the current change, **When** it is applied, **Then** the effective value changes and affected proposals and acceptances are invalidated.
3. **Given** a duplicate or stale confirmation, **When** processed, **Then** it has no effect on current state.
4. **Given** shared handyman availability changes, **When** affected work orders are identified, **Then** each is notified through its own ordered work-order event flow.

### User Story 5 — Route human handoff and silence correctly (Priority: P1)

If the exact incoming body `<NO RESPONSE>` arrives from either participant on an unfinished order, the order enters `RETRYING` instead of closing. The silent role (the role that owes the pending answer) receives a fixed reminder followed by the original unanswered message every `NO_RESPONSE_RETRY_WAIT_SECONDS` (default 300 s, measured on the real UTC clock), at most `NO_RESPONSE_MAX_RETRIES` (default 3) times. If one more wait elapses after the last reminder without an answer, the order ends with `requires_review`. Any normal message from the silent role cancels the retries. The sentinel does not count as approval. If all tenant candidates are blocked and the tenant confirms their requested set is exhausted, the tenant can choose human scheduling even if handyman availability is unknown. Separately, no common time is established only by known complete evidence from both participants. Provider errors and incomplete evidence do not imply silence or impossibility.

**Why this priority**: Human review is the only non-scheduled terminal outcome and must reflect an explicit rule.

**Independent Test**: Send exact and non-exact no-response bodies from either role on unfinished orders; exercise no-response during post-commit finalization, known empty and partial candidate evidence, and verify exactly one valid terminal result.

**Acceptance Scenarios**:
1. **Given** the order is unfinished and the body is exactly `<NO RESPONSE>`, **When** received from tenant or handyman, **Then** the order enters `RETRYING`, is scheduled in the retry heap, and no acceptance is recorded.
1a. **Given** the order is `RETRYING` and the retry wait has elapsed, **When** the poller runs, **Then** the silent role receives the fixed reminder line followed by the original unanswered message, and the order is rescheduled with a new UTC time.
1b. **Given** the order is `RETRYING` and the silent role sends a normal message, **When** it is received, **Then** retries are cancelled and the message is processed normally.
1c. **Given** the order is `RETRYING` and a repeated `<NO RESPONSE>` arrives, **When** it is received, **Then** it is ignored and traced as `no_response_ignored_already_retrying`.
1d. **Given** the order is `RETRYING` and the other role sends a normal message, **When** it is received, **Then** retries continue unchanged.
1e. **Given** all retries were sent and one more wait elapses without an answer, **When** the poller runs, **Then** the order ends with `requires_review` and REASON `No response from <role> while awaiting <action> after <n> retries.`
1f. **Given** stdin reaches EOF while orders are `RETRYING`, **When** EOF is handled, **Then** those orders end with `requires_review` immediately without waiting, traced as `no_response_retries_cut_at_eof`.
1g. **Given** a terminal order with pending retries, **When** it becomes terminal, **Then** its retries are cancelled, and a delayed `<NO RESPONSE>` changes nothing.
2. **Given** evidence is partial or one participant's availability is unknown, **When** no candidate is yet established, **Then** the system asks for the missing information rather than claiming no feasible time.
3. **Given** known complete evidence proves the common eligible set is empty or fully occupied, **When** the tenant accepts human scheduling, **Then** the order ends with `requires_review`; a no answer requests new tenant availability; ambiguity is clarified.
4. **Given** the provider fails, **When** no human message was received, **Then** the failure is not represented as `<NO RESPONSE>` and does not itself create a terminal review result.
5. **Given** an order already committed as scheduled, **When** a delayed `<NO RESPONSE>` arrives during final confirmations, **Then** it cannot change the scheduled outcome.

## Requirements

### Functional Requirements

- **FR-001**: Start coordination for every valid CSV work order and produce exactly one terminal outcome: `scheduled` or `requires_review`. Terminal orders never reopen.
- **FR-002**: Recognize tenant language from the order description, retain it by `(work_order_id, role)`, and address the handyman in Spanish. Recognized tenant languages include the supported catalogue, including Spanish and English; unknown language prompts a neutral multilingual question.
- **FR-003**: Compose every outbound message in the recipient's language. The introduction identifies the incident and uses only grounded order facts.
- **FR-004**: The first scheduling request asks the tenant for all availability as explicit intervals. Merge overlapping/adjacent tenant intervals into their union, then create initial two-hour candidates starting at each union window's start and advancing consecutively; deduplicate equivalent UTC candidates and omit residual intervals shorter than two hours.
- **FR-005**: Candidate intervals derive only from tenant-provided absolute time intervals. The system does not invent calendar availability, a fixed grid, relative-date interpretation, or handyman availability. If an interval is ambiguous, request an absolute interval.
- **FR-006**: Before asking the handyman, pre-filter tenant candidates against the shared agenda and urgency. Immediately ask the tenant for alternatives/all availability for candidates blocked by an equal/higher tentative hold or confirmed appointment; do not ask the handyman about those. Ask the handyman only about free candidates or candidates that could be preempted by strict higher urgency. The handyman may explicitly counter-propose a different full two-hour interval; accept it as a candidate only if it is fully contained in the tenant's original explicit interval union. Pre-filter each counterproposal against the same shared agenda and urgency before asking the tenant to confirm that exact slot. A counterproposal is availability evidence, not consent; both explicit proposal acceptances are still required. Never treat an LLM suggestion as a counterproposal or transfer a tentative hold based on model inference: the requester must select/authorize the candidate, then the schedule authority transfers atomically. The agenda evaluates overlaps across all interval start times. Missing or partial evidence prompts for the missing information.
- **FR-007**: Use UTC instants internally, semi-open `[start,end)` intervals, and the approved `LOCAL_TIMEZONE` presentation zone (default `Europe/Madrid`) for participant-facing times. Do not add new relative-date or DST-specific rules; ambiguous local times require clarification, and a two-hour interval crossing a DST change is deferred to authorized human review under the existing unresolved DST policy.
- **FR-008**: Apply urgency order `Critical > High > Medium > Low` when evaluating an explicitly tenant-requested occupied interval. A request can transfer every overlapping lower-urgency tentative hold atomically only if no overlapping equal/higher hold or confirmed appointment exists. It never displaces a confirmed visit.
- **FR-009**: Notify every displaced tenant in that tenant's language that the held interval is unavailable. Ask them to choose the earliest already-known common eligible interval, sorted by UTC start then stable slot ID; if none exists, renegotiate availability. Do not ask displaced tenants to authorize a transfer.
- **FR-010**: Treat participant availability solely as evidence, never as consent. Obtain explicit yes/no for a specific immutable proposal ID/version from the tenant first, then the handyman. A prior explicit handyman acceptance can be reused only for that exact current proposal version. Ambiguous interpretation is clarification-required, never coerced. When the question concerns exactly one offered slot or proposal, a short natural acceptance ("ok me gusta", "acepto", "me parece bien", "sounds good") is an explicit yes because only one option exists; with several options it is never a yes. A reply with a negation, condition, change request, question, date or time, or longer than a short phrase is not a natural acceptance. An explicit yes or no is recognized from a closed list of Spanish and English variants, with or without accents, with courtesy words ignored (for example "sí, es correcto" or "yes please"). When a yes/no question receives a reply that is neither a yes nor a no and carries no time, the system asks again for a plain "sí" or "no" instead of interpreting it as availability.
- **FR-011**: Bind every interpreted response to its role, unique outstanding question, pending action, proposal version, workflow version and schedule version. Validate these again before mutation. The CLI carries no message version, so an unambiguously unmatched/delayed answer cannot mutate state; when delay is ambiguous, ask the participant to reconfirm the full slot.
- **FR-012**: For an opposite availability update, retain the previous value and suspend the disputed interval until the sender confirms old or new. Confirmed changes invalidate affected proposals and acceptances. Duplicate or stale confirmations have no effect.
- **FR-013**: If every candidate in the tenant's requested set is blocked by a known equal/higher tentative hold or confirmed appointment, ask the tenant for alternatives or all availability before consulting the handyman about those blocked candidates. If the tenant confirms that set is exhausted and no eligible candidate or contained explicit handyman counterproposal remains, ask whether they want human scheduling; yes leads to `requires_review`, no requests new tenant availability, and ambiguity is clarified, even if handyman availability is unknown. Separately, ask about human scheduling when known complete tenant and handyman evidence, including any contained counterproposals, proves no common eligible interval. Unknown or partial handyman evidence alone is not proof of no common availability; request missing information.
- **FR-014**: Only the exact incoming body `<NO RESPONSE>` from tenant or handyman on an unfinished order (`terminal_status` is null) starts the `RETRYING` state: the order is placed in a min-heap keyed by its UTC placement time, reminders are sent to the silent role at most `NO_RESPONSE_MAX_RETRIES` times, and the order closes as `requires_review` only after the final wait elapses. Do not infer that signal from provider or transport errors. Normal messages from the silent role cancel retries; a closed outcome cannot be changed by delayed messages.
- **FR-014a**: The retry settings `NO_RESPONSE_RETRY_WAIT_SECONDS` (default 300), `NO_RESPONSE_MAX_RETRIES` (default 3) and `NO_RESPONSE_POLL_SECONDS` (default 10) are startup-only environment variables read once by Settings. Every setting except `ANTHROPIC_API_KEY` has a default. The retry timer uses the real UTC clock, never the business clock frozen by `--now`; `Date` and relative-date meaning never depend on wall-clock time.
- **FR-015**: Commit atomically only after both explicit acceptances match the same current proposal and schedule revalidation passes. The atomic commit records the immutable appointment, `terminal_status=SCHEDULED`, and `finalization_pending=true`; it cannot be preempted. Send confirmations to both sequentially and idempotently, then emit the scheduled terminal frame. Delivery failure retains the committed scheduled outcome and pending finalization; it cannot free the visit or emit a false frame. `close_review` and scheduled commit are mutually exclusive atomic terminal transitions.
- **FR-016**: Keep one ordered event queue and retained graph state per work order across inbound invocations, while allowing independent work orders to progress concurrently. Shared schedule reads and writes use one authority that serializes all accesses and returns detached immutable snapshots.
- **FR-017**: Handle all transport through the existing CLI contract and an injected common conversation handler. Every outbound message passes language-aware composition. The handler is an I/O port; it does not add a communication channel.
- **FR-018**: Record graph-node transitions and decision evidence including availability, holds/transfers, actor, and versions in existing run-local JSONL traces; redact secrets and provider private reasoning.
- **FR-019**: Keep workflow state process-local; do not promise recovery after process restart. Do not change CSV fields or CLI framing.
- **FR-020**: Do not invent participant evidence, dates, consent, tenant identity, availability, or incident facts.
- **FR-021**: Provide a closed `TerminalStatus` domain enum with exactly `SCHEDULED = "scheduled"` and `REQUIRES_REVIEW = "requires_review"`; keep it null until terminal. Graph cursors and pending actions use separate types. Serialize the enum's exact strings to protocol and trace records.
- **FR-022**: Every `requires_review` outcome MUST carry a structured `ReviewReason` with reason code (`no_response`, `no_common_availability`, or `no_eligible_slot`) and nonempty concise evidence-based detail. Exact no-response records the silent role, current node/question, and known requested tenant intervals. No-common/eligible-slot records tenant-requested windows/candidates, known handyman availability, and blocking schedule facts. Unknown facts are identified as unknown, never invented. Serialize deterministic English in one single-line `REASON:` field; escape line breaks in source values.
- **FR-023**: Preserve the two physical lines of terminal framing. Scheduled output is `WOID:<id>|RESULT:scheduled` then `SCHEDULED_FOR:<aware LOCAL_TIMEZONE ISO datetime>`, emitted after both confirmations. Review output is `WOID:<id>|RESULT:requires_review` then `REASON:<evidence-based detail>`. No third line or status is introduced.
- **FR-024**: Provide meaningful automated coverage for pure interval/priority rules, graph continuation and typed decisions, atomic concurrent schedule access, stale/duplicate responses, terminal idempotency, finalization recovery, structured review reasons, and existing CLI framing. Assert the closed terminal type and exact terminal values, exact two-line output, and distinguish exact `<NO RESPONSE>` from bodies with added characters or whitespace and from delayed signals after commit.

### Key Entities

- **Work Order**: Existing CSV incident and urgency; contains no added tenant identity or language field.
- **Participant**: A work-order tenant or the shared handyman; language is scoped by work order and role.
- **Availability Evidence**: Explicit participant intervals and their effective/disputed status, scoped to an order and role.
- **Visit Candidate**: A tenant-derived, full two-hour interval with a stable ID and UTC start/end.
- **Proposal**: An immutable versioned candidate offered for explicit participant decisions.
- **Tentative Hold**: A proposal's temporary agenda claim, eligible for atomic priority transfer under FR-008.
- **Appointment**: A committed, non-preemptible visit backed by both matching explicit acceptances; commit atomically records the scheduled terminal status.
- **Workflow State**: Retained per-order negotiation state and nullable terminal status; intermediate nodes and waits are not terminal statuses. A separate finalization-pending flag tracks delivery of the already-decided scheduled result.
- **Interpretation Decision**: Typed yes/no/clarification-required evidence bound to the unique outstanding role question and current versions.
- **Audit Event**: Run-local record of graph transitions, decisions, schedule changes and terminal outcome.
- **ReviewReason**: Structured reason code and concise evidence used to produce the single-line `REASON:` second frame line. It is explanation data, never another terminal status.

## Success Criteria

- **SC-001**: Each valid order emits exactly one allowed terminal result; no terminal order reopens.
- **SC-002**: Every scheduled visit has matching current explicit consent from both participants and occupies a conflict-free shared interval.
- **SC-003**: All offers derive from explicit tenant intervals and complete handyman availability evidence; no candidate is invented.
- **SC-004**: All participant-facing messages use the scoped recipient language; handyman messages are Spanish.
- **SC-005**: Same serialized event order yields deterministic urgency, hold-transfer, and tie outcomes; confirmed appointments never overlap.
- **SC-006**: Reversal, stale response, partial evidence, exact no-response, and send failure preserve the rules and produce no false terminal result.
- **SC-007**: Tests can distinguish graph progress, human wait, terminal review, and scheduled finalization, while asserting only the two allowed terminal results.

## Assumptions

- The current read-only CSV and CLI framing remain as documented in `docs/BUSINESS_RULES.md`.
- `Europe/Madrid` is the default presentation zone. UTC is the normalized comparison/storage form.
- Overlapping/adjacent tenant intervals are merged before initial slicing into consecutive two-hour candidates; shorter remainders are ignored. A handyman counterproposal is permitted only when fully contained in that original tenant interval union. No external calendar is available.
- A pending hold is mechanical agenda ownership; it does not itself ask a participant for approval. Participant decisions happen only at consent questions.
- A yes/no interpretation decision is valid only for a unique currently outstanding question. Since stdin messages carry no correlation version, the system cannot perfectly distinguish every delayed duplicate; ambiguous cases require full-slot reconfirmation.
- Existing runtime dependency injection and JSONL trace facilities are reused; this feature introduces no setting, dependency, service, or external channel.
- Policy changes described here are approved for synchronization to `docs/BUSINESS_RULES.md`; implementation remains proposed until separately executed and verified.
