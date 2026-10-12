<!--
Sync Impact Report
- Version change: 1.1.1 → 2.0.1
- Modified principles: all; business and technical authority are now separated.
- Added sections: Normative Sources; Approval Protocol; Runtime Configuration.
- Templates: ⚠ pending update in a subsequent approved documentation change.
- Engram: pending until the connector is available in a new session.
-->
# Maintenance Scheduling Development Constitution

## Core Principles

### I. Normative Sources Are Separate
`docs/BUSINESS_RULES.md` is the sole functional authority. `docs/TECHNICAL_ARCHITECTURE.md` defines
implementation architecture and agent workflow. This document
governs development practice. No document may duplicate or silently override another's authority.

### II. Explicit Developer Approval
Before every code, configuration, documentation, test, structural, or Git change, the coding
agent MUST present objective, source requirements, files, preview, risks, alternatives, and
validation, then ask for explicit developer approval. Approval covers only that concrete scope.
Exceptions require developer approval and a versioned decision record plus an Engram record when
Engram is available.

### III. Deterministic Business Boundaries
LangGraph coordinates work but does not define business policy. Deterministic code enforces
agreement, priority, schedule, terminal, and external-contract rules from `docs/BUSINESS_RULES.md`.
LLM output is validated evidence or proposed language, never scheduling authority.

### IV. Explicit, Typed, Injectable Runtime
Use typed contracts, Pydantic validation, explicit dependency injection, and a single composition
root. Configuration and reusable resources initialize once per process; no hidden global state,
import-time I/O, secret logging, or configuration reload is allowed.

### V. Verifiable Incremental Delivery
Each approved change is small, independently testable, documented, and reported with actual
validation. Tests, traces, graph views, and runtime documentation must distinguish proposed,
implemented, verified, failed, and pending work.

## Runtime Configuration

`ANTHROPIC_API_KEY` is the approved secret source. It is loaded through Pydantic Settings from
environment or `.env` only in the composition root, omitted from Git, logs, and the Docker build
context. `.env.example` contains names without values. Settings changes take effect only on a
new process or container run.

## Governance

Amendments require an explicit developer-approved preview, semantic version update, source and
template review, and a sync report. Major versions redefine authority or principles; minor
versions add material obligations; patches clarify existing obligations. The technical and
business documents may strengthen this constitution but cannot weaken it.

**Version**: 2.0.1 | **Ratified**: 2026-10-12 | **Last Amended**: 2026-10-12
