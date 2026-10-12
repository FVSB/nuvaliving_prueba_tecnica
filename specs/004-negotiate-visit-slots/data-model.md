# Data Model: Negotiate Visit Slots

All records below are proposed process-local state. UTC instants are canonical; externally displayed timestamps use `Europe/Madrid`. Models are immutable or copied at schedule boundaries. Workflow progress is separate from the nullable terminal result.

## WorkOrderContext

- `work_order`: validated existing CSV work order
- `tenant_language`: recognized code or `undetermined`, scoped to tenant role and work order
- `workflow_version`: monotonically increasing per-order mutation version
- `pending_question`: optional unique question ID, role, intent, proposal ID/version and expected workflow/schedule versions
- `terminal_status`: nullable `TerminalStatus`; unset until terminal
- `review_reason`: nullable `ReviewReason`; required exactly when status is `REQUIRES_REVIEW`
- `finalization_pending`: delivery continuation flag; set atomically with scheduled commit and cleared after both confirmations and terminal frame are delivered
- `graph_cursor`: current graph node/wait checkpoint; not a business or terminal status
- **Rules**: terminal status is write-once; state persists for the run; messages for this order process sequentially. `close_review` and scheduled commit race atomically; only the winner closes the order.

## TerminalStatus

Closed domain enum with exactly two members, located with negotiation domain types:

```python
class TerminalStatus(StrEnum):
    SCHEDULED = "scheduled"
    REQUIRES_REVIEW = "requires_review"
```

The exact enum values are the terminal protocol strings. Workflow cursor and pending action use distinct types and can never be added as terminal outcomes without an explicit policy change.

## ReviewReason

Structured explanation attached only to `REQUIRES_REVIEW`; it does not expand `TerminalStatus`:

- `reason_code`: `no_response`, `no_common_availability`, or `no_eligible_slot`
- `detail`: concise deterministic English derived from recorded evidence
- `silent_role`, `current_node`, and `question_id` for no-response closure
- tenant-requested windows, normalized candidates, known handyman windows, and schedule blockers when applicable
- Unknown evidence is represented as unknown. Render one physical `REASON:` line, escaping line breaks in participant input.

## AvailabilityEvidence

- `work_order_id`, `role` (`tenant` or `handyman`), `intervals[]`, `source_question_id`, `revision`, `effective_status`
- Interval values: UTC `start`, UTC `end`; `end > start`; supported effective status is available, unavailable, or unknown.
- Disputed change carries previous and proposed status and confirmation question ID. Preserve previous value, but suspend the disputed interval from proposal and finalization until sender resolves it.
- Handyman evidence is shared agenda evidence and changes may invalidate more than one work order.

## VisitCandidate and Proposal

**VisitCandidate**: stable `slot_id`; work-order association; UTC `start`; UTC `end = start + 2 hours`; source tenant interval revision; optional source handyman counterproposal. Merge overlapping/adjacent original tenant intervals into their union before slicing that union into initial consecutive two-hour candidates. A handyman may explicitly counter-propose a different two-hour interval only when fully contained in the original tenant interval union; it is availability evidence, not consent, and receives the same agenda pre-filter before the tenant is asked to confirm that exact slot.

**Proposal**: immutable `proposal_id`, monotonically increasing proposal version, candidate ID, work-order ID, tenant and handyman evidence revisions, creation schedule version, and state (`offered`, `superseded`, `committed`). Stable slot IDs deduplicate equivalent UTC starts; different starts that overlap are distinct candidates and are adjudicated by interval overlap.

Every participant decision references one proposal ID/version and the unique outstanding role question. A decision is not copied to a replacement proposal.

## TentativeHold and Appointment

**TentativeHold**: hold ID, owner work order, proposal ID/version, UTC interval, urgency, and schedule version. Holds are temporary, mechanical agenda ownership and are not consent. Higher urgency may atomically transfer all overlapping lower-urgency holds only when no overlapping equal/higher hold or appointment exists.

**Appointment**: immutable appointment ID, work order, committed proposal ID/version, UTC interval, both participant acceptances, and commit schedule version. Atomic commit also sets `terminal_status=SCHEDULED` and `finalization_pending=true`. The appointment cannot be preempted. The scheduled terminal frame follows sequential delivery of confirmations to both.

Intervals are semi-open `[start,end)`, allowing adjacent visits. The authority checks overlaps across all starts, including proposals that do not share an initial slice boundary. Every agenda read and write uses the one shared authority, which returns detached snapshots and serializes all access.

## ParticipantDecision

- `question_id`, participant role, `pending_action`, `proposal_id`, proposal version, workflow version, schedule version
- `decision`: `yes`, `no`, or null; `clarification_required`: boolean
- **Rules**: output is typed/validated; ambiguous input remains clarification-required. Before state mutation the question must still be the unique outstanding question for that role and all relevant versions must match. Stdin has no message version; an ambiguous delayed answer is re-asked against the full slot.

## AuditEvent

- run timestamp, work-order ID, event type, actor/role, detail, workflow version, proposal version, schedule version
- Records node transitions, interpretation decisions, availability changes, hold acquisition/transfer/release, commit, confirmation delivery, and terminal transition.
- Redact credentials and provider private reasoning. Existing JSONL writer remains the append mechanism.

## State Transitions

Graph progress may move through language recognition, tenant availability request/wait, candidate creation, handyman availability request/wait, proposal/consent request/wait, confirmation, and terminal finalization. These are graph cursors and pending questions, not terminal business statuses.

```text
active negotiation ── exact <NO RESPONSE> ──> RETRYING (reminders in retry heap)
RETRYING ── normal message from silent role ──> active negotiation (retries cancelled)
RETRYING ── retries exhausted + one more wait, or EOF ──> requires_review + role/question reason
active negotiation ── confirmed no common time + tenant yes ──> requires_review + availability evidence reason
active negotiation ── matching tenant+handyman yes + atomic commit ──> scheduled (finalization pending)
```

Every other path remains active, requests missing information, clarifies a response, or creates a new proposal. `<NO RESPONSE>` starts `RETRYING` only for an order whose terminal status is still null; it closes as `requires_review` only after the retries are exhausted and one more wait elapses (or at EOF). `RETRYING` is a negotiation sub-state, not a terminal status; delayed messages during scheduled finalization cannot change it. There is no third terminal status.
