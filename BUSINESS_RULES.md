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
- The handyman is always addressed in Spanish. The tenant is addressed in the language of the
  order, Spanish or English.
- Start all CSV orders on container startup without awaiting any previous conversation. Receive
  messages for every unfinished order in arbitrary order.
- Only a body exactly equal to `<NO RESPONSE>` is a human-timeout event. Do not use wall-clock
  timeouts or treat provider failure as human absence.

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
SCHEDULED_FOR:<ISO-8601 Europe/Madrid datetime>
```

```text
WOID:<work_order_id>|RESULT:requires_review
REASON:<brief reason>
```

Normal stdout and stderr contain protocol data only. Traces and runtime logs go to
`/app/traces` as JSONL; every functional event records timestamp, work-order ID, event type,
and detail. Commit an example trace from a real complete run.

## Agreement and Scheduling Invariants

Availability is not acceptance. Both acceptances must match the same current proposal; a changed
visit invalidates old acceptance. A complete two-hour interval is required. Consecutive intervals
that only meet at their boundary do not overlap. Revalidate the shared schedule immediately
before consolidation. Never invent availability, consent, or dates.

## Pending Policies Requiring Approval

- Tenant-language inference where the CSV lacks a language field.
- Reference clock for relative dates such as “tomorrow”.
- Finite handling of repeated `<NO RESPONSE>` and clarification attempts.
- Tie-breaking and late competition between equal or newly higher urgencies.
- Invalid/duplicate CSV rows, malformed input, unknown IDs, EOF, and terminal-result separator.
- DST semantics for a two-hour visit.

These policies are not implemented merely by being listed. Changes require source, rationale,
developer approval, and a documented decision.

## Delivery

Provide a root Dockerfile. The evaluator uses Docker only and runs the container with `.env`,
the read-only CSV mount, and `/app/traces` volume as defined here. Do not commit `.env`; provide
`.env.example` without secrets. Contact external parties only with developer authorization.
