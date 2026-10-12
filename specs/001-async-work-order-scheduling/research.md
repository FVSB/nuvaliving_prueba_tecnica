# Research: Async Work-Order Scheduling

## Decision: Use durable, typed LangGraph state with a per-run thread identifier

**Rationale**: LangGraph treats state as shared data between nodes and recommends retaining raw
values that must survive later steps. Its checkpoints support pause/resume and retries; use one
run identifier as the graph thread identifier and persist the domain identifier in state.

**Alternatives considered**:

- An in-memory graph: rejected because a restart loses asynchronous work and retry context.
- A large, single scheduling node: rejected because import errors, state changes, and retries
  cannot be independently observed or extended.

Source: [LangGraph workflow design guidance](https://docs.langchain.com/oss/javascript/langgraph/thinking-in-langgraph).

## Decision: Make PostgreSQL the authority for capacity and idempotency

**Rationale**: The graph's availability node is advisory. A transaction that writes the hold or
appointment must enforce the two-hour, capacity-one rule and claim the work idempotently. Store
appointments as UTC time ranges and prevent intersection through a database exclusion constraint
or equivalently robust serializable transaction. Record the idempotency key with a unique
constraint.

**Alternatives considered**:

- Checking availability in memory before writing: rejected because concurrent requests race.
- Trusting a graph checkpoint as the booking record: rejected because it does not enforce a
  database-level capacity constraint.

## Decision: Keep Anthropic outside the booking decision path

**Rationale**: CSV parsing, tenant isolation, priority ordering, and capacity checks have
deterministic rules. Anthropic may later draft a tenant-facing message after a recorded outcome,
but its structured output is validated and cannot alter a reservation without the same domain
transaction.

**Alternatives considered**:

- Asking a model to rank or schedule WOs: rejected because the ordering and conflict invariants
  must be reproducible and auditable.

## Decision: Submit imports to a durable queue and process rows asynchronously

**Rationale**: The HTTP caller receives an import-job identifier immediately, while a worker
streams rows through the graph. Row-level outcomes make partial input failures visible without
discarding correct WOs. The queue message references stored file metadata instead of carrying
the whole CSV.

**Alternatives considered**:

- Processing the CSV in the HTTP request: rejected because it is vulnerable to timeout and
  cannot be resumed safely.
