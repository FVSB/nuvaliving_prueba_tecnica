<!--
Sync Impact Report
- Version change: template → 1.1.1
- Modified principles: IV. Incremental, Independently Verifiable Delivery → IV. Incremental,
  Independently Verifiable Delivery and Gitflow.
- Added sections: Technical Constraints; Development Workflow and Quality Gates; Gitflow Policy.
- Removed sections: none.
- Templates requiring updates:
  ✅ .specify/templates/plan-template.md
  ✅ .specify/templates/spec-template.md
  ✅ .specify/templates/tasks-template.md
  ✅ .specify/templates/commands/ (directory absent; no files to update)
  ✅ AGENTS.md (already directs developers to the current plan)
- Deferred TODOs: none.
-->
# HandyMan Scheduler Constitution

## Core Principles

### I. Tenant Isolation Is Mandatory
Every request, state transition, query, appointment, availability record, and audit event MUST
carry a validated tenant identifier. Data access MUST scope by that identifier, and a tenant
MUST never read or modify another tenant's data. Cross-tenant behavior requires an explicit,
documented administrative use case and an authorization check. This protects each tenant's
customers and scheduling data while they share one handyman.

### II. One Handyman, Conflict-Free Appointments
The system MUST model one shared handyman as a capacity-one resource. It MUST reject an
appointment that overlaps an existing confirmed or held booking, using the authoritative
timezone and atomic persistence rule. Cancellation, expiration, and rescheduling MUST release
or replace capacity without creating a double booking. This is the core business guarantee.

### III. LangGraph State Is Explicit and Durable
Every scheduling workflow MUST be represented by named LangGraph nodes, typed state, and
explicit transitions. Each node MUST have a single stated responsibility, validate the state it
consumes, and produce only its documented state changes. State that crosses process or retry
boundaries MUST be checkpointed or persisted; graph transitions and failures MUST be traceable.
This makes incremental nodes safe to add, test, and operate.

### IV. Incremental, Independently Verifiable Delivery
Work MUST be delivered in thin vertical slices. Each slice MUST name its user outcome, graph
nodes and state changes, acceptance criteria, and an independent verification path before the
next slice begins. New nodes MUST preserve the behavior of completed flows. Tests are required
for tenant isolation, scheduling conflicts, and every changed graph branch; external-model calls
MUST be replaceable with deterministic test doubles. This keeps the application buildable as it
grows step by step.

### V. Gitflow Is the Delivery Boundary
`develop` is the integration branch for active development. Every feature MUST start from the
latest `develop` as a new `feature/<feature-name>` branch, be implemented and tested there, and
merge back into `develop` only after its specified acceptance checks pass. A completed feature branch MUST NOT
be reused for new feature work. A later modification MUST be evaluated with the user before it
starts: create `fix/<issue-name>` from `develop` for a defect, or create a new feature branch when
it changes intended behavior. This keeps work traceable and avoids silently reopening merged
history.

### VI. Anthropic Credentials and AI Boundaries
Anthropic access MUST use an API key supplied only through runtime configuration or a managed
secret store; keys MUST never be committed, logged, returned to clients, or embedded in prompts.
The Anthropic-backed node MUST validate inputs and model output before it can affect booking
state. Deterministic rules remain the authority for tenant access, availability, and conflict
resolution. This confines probabilistic behavior and prevents credential exposure.

## Technical Constraints

The application MUST use LangGraph for orchestration and support configuration through the
`ANTHROPIC_API_KEY` environment variable. Production configuration MUST fail clearly when a
required key is missing, without revealing the key. The initial product supports several tenants
booking the same named handyman; expanding to multiple handymen requires a constitution
amendment or an approved feature-specific exception.

All persisted timestamps MUST be stored in UTC and presented using an explicitly selected
timezone. Appointment lifecycle values and graph state schemas MUST be versioned whenever a
change can affect persisted work or retries.

## Development Workflow and Quality Gates

Each feature specification MUST identify tenant boundaries, appointment capacity effects,
LangGraph nodes and state fields, Anthropic use if any, failure paths, and how the slice is
tested. Plans MUST pass the Constitution Check before implementation and again after design.

Before a slice is complete, automated checks MUST cover its graph transition paths and the
relevant isolation and overlap invariants. Logs MUST use structured fields for request ID,
tenant ID, workflow or appointment ID, node name, transition result, and failure category; they
MUST exclude API keys and customer-sensitive prompt content unless explicitly redacted.

## Gitflow Policy

`develop` is the sole parent for `feature/*` and `fix/*` branches. Each feature branch is named
after its feature, receives implementation and tests in isolation, and is merged into `develop`
when ready.
Before any follow-up to merged work, the maintainer MUST ask the user whether it is a correction
(`fix/<issue-name>`) or a new behavior (`feature/<feature-name>`); work then begins from the
latest `develop`. Merging `develop` into the old branch to continue it is not the default and requires
the user's explicit decision.

## Governance

This constitution governs all implementation plans, specifications, tasks, reviews, and runtime
guidance. A change requires a documented amendment, its semantic version change, an update to
affected templates and guidance, and a compliance review. A MAJOR version removes or redefines
a principle incompatibly; a MINOR version adds a principle or material obligation; a PATCH
version clarifies existing guidance without changing obligations.

Every plan and review MUST record compliance with the six principles or justify a temporary
exception, its owner, expiry, and remediation. The current plan and any feature quickstart are
the operational references for implementation details; they may add stricter constraints but
may not weaken this constitution.

**Version**: 1.1.1 | **Ratified**: 2026-10-12 | **Last Amended**: 2026-10-12
