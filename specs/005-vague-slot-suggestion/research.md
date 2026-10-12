# Research: Vague Date Request Handling with Deterministic Slot Table

**Feature**: 005-vague-slot-suggestion | **Date**: 2026-10-12

## Decision 1: Message classification placement

**Decision**: Classify inside the extended availability-interpretation call (one Anthropic call
returning a routing verdict plus intervals), rather than a separate standalone classifier node.

**Rationale**: `AnthropicConversationHandler.interpret_availability` already parses tenant text
with calendar tools; a `vague_date_request` verdict plus any partial intervals fits the existing
`AvailabilityInterpretation` output without a second provider call. The workflow routes on the
verdict before its existing branches in `_tenant_availability` (workflow.py:162).

**Alternatives considered**: (a) separate LangGraph classification node with its own LLM call —
rejected: doubles provider calls and duplicates calendar resolution; (b) pure keyword/regex
detection — rejected: multilingual input ("esta semana", "weekday mornings") makes it unreliable.

## Decision 2: Source and window of "open" slots

**Decision**: Open slot = two-hour interval in a fixed presentation grid over the 7 local days
starting at the reference day (approved `LOCAL_TIMEZONE`), that overlaps no confirmed appointment
or tentative hold in the shared agenda snapshot. Fixed daily start/end hours bound the grid. The
table carries a fixed disclaimer that agenda-open slots do not guarantee handyman availability.

**Rationale**: User-approved (FR-012 option A, FR-013: 7 days). `docs/BUSINESS_RULES.md` forbids
inventing handyman availability, so the table only asserts shared-agenda occupancy; the
disclaimer keeps the claim honest. The grid is presentation-only: it is never sliced into
candidates nor treated as tenant consent, preserving the 004 invariant "do not invent a fixed
grid" for *candidate derivation* (candidates still come only from tenant-supplied intervals).

**Alternatives considered**: (a) handyman-evidence-only table — rejected: empty for fresh orders;
(b) ISO-current-week window — rejected: empties near week end; (c) 14 days — rejected: table
size.

**Open policy point (needs developer sign-off at implementation approval time)**: the fixed
daily start/end hours (proposed 09:00–19:00 local) are a new presentation constant, not a
business-policy change; they only shape the suggested table.

## Decision 3: Deterministic table rendering

**Decision**: The markdown table is produced by deterministic code from the agenda snapshot:
fixed columns (slot ID, local date, weekday, start–end, status), ordered by UTC start then slot
ID; identical input produces byte-identical output. The LLM composes only the prose around the
table; the table block itself is injected verbatim into the composed message or the reply is
assembled deterministically around an LLM-composed intro line.

**Rationale**: Constitution Principle III (LLM output is proposed language, never scheduling
authority) and spec SC-001 (byte-identical determinism). An LLM cannot be trusted to reproduce a
table exactly.

**Alternatives considered**: full-message LLM composition with the table in the prompt —
rejected: non-deterministic and harder for the validator to check byte-exactly.

## Decision 4: Validation gate and retry loop

**Decision**: A separate validator invocation (same Anthropic handler, distinct prompt) receives
the drafted reply, the agenda snapshot data, and the deterministic table, and returns a structured
verdict (valid / invalid + feedback). The workflow loop regenerates on failure with the feedback
appended to the composer prompt; attempt counter caps at 3; on the 3rd failure the deterministic
fallback reply (no LLM) is emitted. Retry and outcome are traced as JSONL events.

**Rationale**: User requirement; matches Constitution Principle III (validated evidence) and the
tracing rules of `docs/BUSINESS_RULES.md` (timestamp, work-order ID, event type, detail). A
deterministic pre-check (table bytes, slot openness recomputed from the snapshot) runs before the
LLM validator so most failures are caught cheaply.

**Alternatives considered**: (a) deterministic validation only, no LLM validator — rejected: user
explicitly asked for a second LLM check; (b) unbounded retries — rejected: user specified 3.

## Decision 5: Fallback reply

**Decision**: Fully deterministic template in the tenant's recognized language: "be more
specific", the next open slot computed from the snapshot (earliest by UTC start, stable slot ID),
and the request for explicit intervals. Rendered from language templates, not LLM composition.

**Rationale**: Guarantees a valid, honest reply after repeated composition failures; language
templates already exist as a pattern via compose intents and the recognized language from
Feature 003.

**Alternatives considered**: re-asking generic complete availability — rejected: that is exactly
the failure mode this feature removes.

## Decision 6: State integration

**Decision**: Extend `AvailabilityInterpretation` with the classification verdict and route
inside `_tenant_availability`; keep `GraphCursor` at tenant-availability semantics by adding a
`SLOT_SUGGESTION` cursor value and `PendingAction` entries, with the pending question remaining
the tenant availability question so the existing message-routing guards (role/action match) keep
working. Retry counter stored in workflow state, reset per inbound tenant message.

**Rationale**: Smallest change to the existing graph; the 004 contracts (`specs/004-negotiate-visit-slots/contracts/negotiation.md`) remain intact; acceptance suite of 004 must pass
unmodified.

**Alternatives considered**: full LangGraph subgraph rewrite — rejected: scope.
