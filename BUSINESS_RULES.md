# Business Rules and Binding Contract

## Authority and Scope

This document is the binding functional source for the scheduling solution.
`TECHNICAL_ARCHITECTURE.md` defines implementation mechanics.

## Binding Contract

- Start coordination for every valid work order in `/app/work_orders.csv`.
- Produce exactly one terminal result per work order: `scheduled` or `requires_review`.
- Emit `scheduled` only after tenant and handyman explicitly accept the same identifiable visit.
  Send confirmations to both before the terminal result. A terminal order never reopens.
- One handyman serves every order. Visits last exactly two hours, never overlap, use
  `Europe/Madrid`, and competing known availability favors `Critical > High > Medium > Low`. Local
  time defaults to `Europe/Madrid` and is set once at startup through the approved `LOCAL_TIMEZONE`
  setting.
- The handyman is always addressed in Spanish. The tenant is addressed in the recognized language
  for that work order; language is scoped to `(work_order_id, role)`, with no cross-order identity
  inference. If language is unknown, ask neutrally in multiple languages.
- Start all CSV orders on container startup without awaiting any previous conversation. Receive
  messages for every unfinished order in arbitrary order.
- Only a body exactly equal to `<NO RESPONSE>` from tenant or handyman on an unfinished order is a
  human-timeout event: atomically close it as `requires_review` immediately, with no retry or
  approval. Prefix/suffix/whitespace variants do not match. A delayed message cannot change a
  terminal result. Do not use wall-clock timeouts or treat provider failure as human absence.
- A malformed inbound CLI line (no `|` separator or an invalid role, so no sender can be
  identified) is ignored, logged to the current run's `runtime.jsonl` as `malformed_input` with its
  length, validation reason, and submitted line, and does not stop the process. A line with a
  valid work order id and role but an empty or oversized body, or an unknown work order id, is
  instead answered with a fixed reply (see Agreement and Scheduling Invariants) and traced as `message_rejected`.

## External Interfaces

The read-only CSV path is `/app/work_orders.csv` and its exact schema is:

```csv
work_order_id,work_order,address,description,reported_at,urgency
```

Do not change the CSV, require extra columns, or confuse `reported_at` with a visit time.

Outgoing messages are emitted as a complete, flushed block:

```text
WOID:<work_order_id>|ROLE:tenant|handyman
<message body>

```

Incoming messages have this form. `role` is the sender; preserve the full body, including `|`.

```text
<work_order_id>|<role> <message body>
```

Terminal output is exactly one of:

```text
WOID:<work_order_id>|RESULT:scheduled
SCHEDULED_FOR:<ISO-8601 LOCAL_TIMEZONE datetime>
```

```text
WOID:<work_order_id>|RESULT:requires_review
REASON:<brief reason>
```

Preserve exactly these two physical lines. For `scheduled`, `SCHEDULED_FOR` contains the aware
`LOCAL_TIMEZONE` ISO datetime (the approved setting defaults to `Europe/Madrid`). For
`requires_review`, `REASON` is one deterministic English line
derived from a structured `ReviewReason` code and recorded evidence. Codes are `no_response`,
`no_common_availability`, and `no_eligible_slot`; this is explanation data, not a third status.
No-response detail names the silent role and current node/question, with requested tenant intervals
when known. Availability detail includes tenant-requested windows/candidates, known handyman
availability, and schedule blockers. If information is unknown, say so; never invent it. Escape
newlines in participant-supplied values so the frame remains two lines. Do not include model private
reasoning.

Examples:

```text
WOID:WO-002|RESULT:scheduled
SCHEDULED_FOR:2026-10-08T18:00:00+02:00
```

```text
WOID:WO-003|RESULT:requires_review
REASON:No mutually acceptable visit time: tenant requested 2026-10-08 09:00–11:00 Europe/Madrid; handyman available 2026-10-08 12:00–14:00 Europe/Madrid; no common two-hour interval.
```

```text
WOID:WO-004|RESULT:requires_review
REASON:No response from handyman while awaiting availability for tenant-requested 2026-10-08 09:00–11:00 Europe/Madrid.
```

Normal stdout and stderr contain protocol data only. Traces and runtime logs go to
`/app/traces` as JSONL; every functional event records timestamp, work-order ID, event type,
and detail. Commit an example trace from a real complete run.

## Agreement and Scheduling Invariants

Availability is not acceptance. Both explicit acceptances must match the same immutable current
proposal ID/version; a changed visit invalidates old acceptance. A complete two-hour interval is
required. Consecutive intervals that only meet at their boundary do not overlap. Revalidate the
shared schedule immediately before mutation. Never invent availability, consent, or dates.

Negotiation begins by asking the tenant for all explicit availability intervals. Normalize them to
absolute time and split from each stated start into consecutive two-hour candidates; ignore a
residual shorter than two hours. Do not invent calendar availability, relative dates, or handyman
availability. The only fixed grid allowed is the presentation-only slot table of Feature 005
(7 local days, two-hour slots, 09:00-19:00, shown for vague date requests); it only reports
shared-agenda occupancy and is never candidate, consent, or availability evidence. Ask the handyman only about tenant-derived candidates that survive agenda
pre-filtering. A candidate occupied by an equal/higher-urgency tentative hold or confirmed visit is
immediately returned to the tenant for alternatives. A free or strict-higher-urgency-preemptible
candidate may be asked of the handyman. A selected tenant request transfers all overlapping lower-
urgency tentative holds atomically, only if no equal/higher hold or confirmed visit overlaps. No
transfer occurs from model inference alone. Confirmed appointments are immutable and never
preempted. Notify displaced tenants in their language; offer the earliest already-known common
eligible block ordered by UTC start and stable slot ID, otherwise renegotiate.

Merge overlapping or adjacent tenant windows into their union before slicing initial candidates.
The handyman may explicitly counter-propose a different full two-hour interval only when it is
fully contained in the tenant's original interval union. Check that interval against the shared
agenda and urgency rules, then ask the tenant to confirm the exact slot. A counterproposal is
availability evidence, never tenant consent. The shared agenda checks all intervals by overlap,
including different start times that do not align with the initial two-hour slices.

When known, complete tenant and handyman evidence proves there is no common eligible interval, ask
the tenant whether they want human scheduling. Yes closes as `requires_review`; no
asks for new tenant availability; ambiguity is clarified. Partial or unknown evidence is not proof
of impossibility and requires missing information.

If shared-agenda pre-filtering blocks every candidate in the tenant's requested set, ask the tenant
for alternatives or all availability without querying the handyman about those blocked intervals.
Once the tenant confirms the set is exhausted and no eligible candidate remains, offer human
scheduling. A yes closes as `requires_review`; a no requests new tenant availability. This
no-eligible-slot case is established by the complete tenant request set and known agenda blockers,
even when handyman availability is unknown; it is distinct from claiming there is no common
availability based on incomplete evidence.

Availability reversals from either participant require confirmation by that sender. Preserve the
previous value but suspend the disputed interval from proposals and finalization until resolved.
Confirmed changes invalidate affected proposals and acceptances.

Terminal statuses are represented by a closed `TerminalStatus` type with exactly `scheduled` and
`requires_review`; its value is null before terminal. Atomic commit of a mutually accepted proposal
sets `scheduled`, installs an immutable non-preemptible appointment, and marks finalization pending.
Review closure and scheduled commit are mutually exclusive atomic transitions. Send confirmations
sequentially/idempotently to both before emitting the scheduled terminal frame. A send failure keeps
the appointment and pending finalization; it cannot free the time or emit a premature frame. Graph
progress and pending questions are not terminal statuses. Use the approved `LOCAL_TIMEZONE` display
zone (default `Europe/Madrid`) and UTC comparison instants. Ambiguous local time requires
clarification. Daylight-saving transitions need no special policy: offsets come from the IANA
timezone database and visits run only 09:00-19:00, never during the overnight transition.

Every inbound participant message except the exact `<NO RESPONSE>` sentinel passes a prompt-injection
guard before any workflow logic. When an Anthropic credential is configured, the guard asks a
structured yes/no question with a self-reported probability; a probability strictly above
`INJECTION_THRESHOLD` (default 0.6) triggers extraction of the suspect fragment, a second
assessment of that fragment alone, and, if confirmed, removal of the fragment with deterministic
code followed by a third assessment of the remainder. A clean non-empty remainder continues as the
only content of the message; otherwise the message is not processed and its sender receives a
fixed localized security notice followed by the last message previously sent to that role. The
guard is evidence only and fails open on provider errors, which are recorded in `runtime.jsonl`;
deterministic validation downstream remains authoritative. Urgency comes only from the CSV, never
from message text.

Visits are allowed only between 09:00 and 19:00 `Europe/Madrid`: the whole two-hour visit, start
and end, must fall inside that window. Availability or a proposal dated in the past, more than
`VISIT_HORIZON_DAYS` natural days ahead (default 7), outside visit hours, with a non-existent
date/time, or whose stated weekday disagrees with the calendar date is rejected by deterministic
code, never recorded as availability, and answered to its sender with the reason and a new request.
Model output is evidence only and cannot override this check.

An inbound message for an unknown work order, with an empty body, or longer than
`MAX_MESSAGE_LENGTH` characters (default 2000) is rejected before any model call and its sender
receives a fixed Spanish/English reply (bilingual when the language is unknown). A participant cancelling a pending proposal is treated as rejecting it.

## Pending Policies Requiring Approval

- Invalid/duplicate CSV rows, unknown IDs, EOF, and terminal-result separator.
- Reference clock for interpreting relative dates such as “tomorrow”.

Policies 005-visit-negotiation records the user-approved rules above. They are binding policy
changes, not evidence of implementation. Other open policies remain unresolved and out of Feature
004 scope. Changes require source, rationale, developer approval, and a documented decision.

## Delivery

Provide a root Dockerfile. The evaluator uses Docker only and runs the container with `.env`,
the read-only CSV mount, and `/app/traces` volume as defined here. Do not commit `.env`; provide
`.env.example` without secrets. Contact external parties only with developer authorization.
