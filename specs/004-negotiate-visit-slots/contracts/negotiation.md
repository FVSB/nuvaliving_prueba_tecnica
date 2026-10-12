# Negotiation Contracts (Proposed)

These are internal contracts for the planned implementation; they do not change the existing stdin/stdout framing. Domain policies and schemas are authoritative in the feature spec. This feature has no new external API.

## ConversationHandler

The planned `ConversationHandler`, `MessageInterpreter`, and `MessageComposer` application ports are adapted to the existing CLI by `cli_conversation.py`; this adds no communication channel. The adapter routes inbound messages into coordinator queues. Graph nodes never read stdin or block while awaiting future participant input. Each graph invocation emits an outbound intent and pending question, then yields. A later queued inbound event resumes retained state. Invocation context includes:

```text
work_order_id, current_node, role, pending_action, question_id,
workflow_version, proposal_id/version?, schedule_version?, approved_intent, grounded_data
```

The handler routes the full inbound body and sender role, or reports I/O failure distinctly. A provider/transport failure is never translated into human `<NO RESPONSE>`. `anthropic_conversation.py` implements typed interpretation and composition using the same injected startup client; tests use fakes. All outbound text is produced by `compose_message` using the role-scoped language and grounded approved data, then passed through the handler and existing CLI writer.

## Availability Interpretation

Typed result: explicit absolute intervals and the participant's asserted available/unavailable evidence, or clarification-required. The result is bound to the outstanding question and validated against work order, role, question ID, workflow version and schedule version. Invalid or ambiguous time input requests clarification; it cannot create availability.

Merge overlapping/adjacent explicit tenant intervals into their union before slicing initial consecutive two-hour candidates. The handyman may return a counterproposal for a different full two-hour interval only when that interval is fully contained in the original tenant interval union. This is availability evidence, never consent. Run the same occupancy/priority pre-filter for that interval, then ask the tenant to confirm that exact slot. The shared authority checks overlap across arbitrary UTC starts, even when they do not align with initial slices.

## Confirmation Decision

The application does not ask the language model to decide consent. A deterministic domain function
recognizes only short, explicit yes/no replies; availability statements, conditional replies, and
ambiguous language remain unresolved and trigger clarification.

```text
decision: yes | no | null
clarification_required: boolean
role: tenant | handyman
question_id: unique outstanding question
proposal_id: immutable proposal identifier
proposal_version: current proposal version
workflow_version: state version observed by interpreter
schedule_version: schedule version observed by interpreter
```

Before applying a decision, the coordinator verifies the unique outstanding role question, current proposal and work-order state. If the global schedule version changed, it atomically re-evaluates the candidate and overlapping occupants against the current snapshot; unrelated interval changes do not invalidate the question by themselves. A stale proposal or role question is rejected. Ambiguous input is `decision=null` and `clarification_required=true`, never coerced to yes/no. Because incoming CLI messages have no version, uncertain delayed messages request full-slot confirmation.

## ScheduleAuthority

All public operations serialize every agenda read and write under one `asyncio.Lock`. Read methods return detached immutable snapshots. Mutation operations atomically revalidate relevant proposal, candidate and occupant state, then apply a complete transition:

- `inspect_candidates`: pre-filter candidates by current occupancy/urgency before handyman questions.
- `acquire_or_transfer_hold`: called only after the requester selected/authorized a candidate; transfer all overlapping lower-urgency tentative holds only if no equal/higher hold or confirmed visit blocks it.
- `apply_availability_change`: update evidence and invalidate affected proposals/acceptances.
- `commit_appointment`: validate both current acceptances and no overlap, then install an immutable appointment and atomically set `terminal_status=SCHEDULED`, `finalization_pending=true`.
- `close_review`: atomically set `terminal_status=REQUIRES_REVIEW` only while status is null. It races mutually exclusively with commit.
- `release_hold`: release only a matching current tentative hold; committed appointments cannot be released or preempted by negotiation.

No operation holds the agenda lock across conversation, model, human, or output waits. Cross-work-order consequences are emitted as internal versioned events after atomic mutation and processed on each affected order's queue.

## TerminalStatus and Protocol

The terminal model is `TerminalStatus(StrEnum)` with exactly `SCHEDULED = "scheduled"` and `REQUIRES_REVIEW = "requires_review"`; state stores `None` before terminal. Its exact `.value` is written to existing terminal frame format. Graph cursor/wait phases and pending actions are not terminal status values.

Scheduled commit records the terminal domain outcome immediately, then sends confirmations sequentially and idempotently before emitting the terminal protocol frame. Failed delivery retains the appointment and pending finalization; no frame is emitted prematurely. Exact incoming `<NO RESPONSE>` from either participant closes only an unfinished order as `requires_review`; extra prefix, suffix, or whitespace does not match, and a delayed signal cannot change scheduled status.

## Serialization and Trace

Every review closure also carries structured `ReviewReason` data with code `no_response`, `no_common_availability`, or `no_eligible_slot`, plus concise evidence-based detail. No-response includes role and current node/question. Availability reasons include tenant-requested windows/candidates, known handyman windows, and blocking schedule facts. Unknowns are labeled unknown, not filled in. Detail renders as one deterministic English line; source newlines are escaped. This explanation object does not add a terminal status.

`no_eligible_slot` is established after all tenant candidates have been pre-filtered as blocked and the tenant confirms their requested set is exhausted, with no contained handyman counterproposal left to evaluate; handyman availability may still be unknown. `no_common_availability` requires known complete evidence from both tenant and handyman, including contained counterproposals, showing no common eligible interval. Do not use unknown handyman availability alone as evidence for `no_common_availability`.

The existing two-line terminal framing is preserved:

```text
WOID:WO-002|RESULT:scheduled
SCHEDULED_FOR:2026-10-08T18:00:00+02:00
```

```text
WOID:WO-003|RESULT:requires_review
REASON:No mutually acceptable visit time: tenant requested 2026-10-08 09:00–11:00 Europe/Madrid; handyman available 2026-10-08 12:00–14:00 Europe/Madrid; no common two-hour interval.
```

Keep current CLI message framing. Preserve full inbound bodies. The terminal writer emits exactly the business-rule terminal frame. Use existing run-local JSONL trace infrastructure; include event type and actor, work-order and relevant versions, but redact secrets and model private reasoning.
