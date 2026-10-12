---
name: maintain-runtime-configuration
description: Maintain startup-only configuration, dependency-injector wiring and run-scoped JSONL logging for the NUVa scheduling agent, with approval, synchronized documentation and Engram records. Use when adding or changing application settings or logging; not for live reconfiguration.
---

# Maintain Runtime Configuration

## Scope and sources

Use this skill for the NUVa scheduling application. Read its technical architecture, business rules and current configuration guide before changing settings or logging. From the repository root, those files are `docs/TECHNICAL_ARCHITECTURE.md`, `docs/BUSINESS_RULES.md` and `docs/configuration.md`.

The PDF controls business behavior and external contracts. Engram is development memory, not a runtime prerequisite or a stronger authority than current files.

## Approval boundary

- Inspect current Settings, bootstrap, container and logger before proposing a change.
- For a potentially configurable parameter, ask whether the user wants an environment variable loaded once at startup and injected through dependency-injector. Present name, type, default, validation, consumer, secret status, impact and restart requirement.
- Approve business policy separately before making its value configurable. Never expose PDF invariants as environment overrides, including Madrid timezone, visit duration, handyman count or evaluation paths.
- Show the intended diff and tests; obtain explicit approval for that change. This workflow belongs to the coding agent, never the evaluated CLI.

## Startup-only implementation

- Read environment once through validated Pydantic Settings in the composition root; freeze the effective snapshot.
- Populate dependency-injector once and inject resources explicitly. Do not fetch settings from a global container inside nodes.
- Create clients, run context, logger and trace sink once; manage their shutdown once.
- No file watchers, repeated getenv, config reload, runtime setters or provider overrides in production. Isolated test overrides must not leak into production or other tests.
- A setting change requires a new authorized process/container run; do not interrupt an active coordination run automatically.

## Logging invariants

- Runtime logs and functional traces are JSONL under `/app/traces` only, with no console handlers or unrelated stdout/stderr.
- Use one folder per run, named by Madrid start timestamp with offset and a unique run ID; keep it across hour/day changes.
- Correlate by run ID, event sequence and work-order ID; global events use explicit application scope and null order ID.
- Preserve all required functional events regardless of technical log level. Serialize concurrent writes, avoid duplicate handlers and flush critical events/shutdown.
- Redact secrets before snapshots, error logging or memory writes. Log timestamps do not trigger human timeouts or define the business meaning of relative dates.

## Documentation and Engram

Synchronize approved changes across Settings, container, `.env.example`, `docs/configuration.md`, decision notes, tests and this skill when its procedure changes. Mark proposed versus implemented parameters and never store real secret values.

Consult Engram context/search at the start when available. Save approved decisions and verified results using separate stable topics such as `architecture/runtime-configuration` and `architecture/run-logging`; include what, why, affected paths, effective lifecycle and required restart. Correct existing observations with their stable topic or exact ID instead of overwriting unrelated topics.

If Engram is unavailable, keep the versioned documentation and report the pending memory write. Do not claim memory saved or application implemented without successful readback/evidence.

## Verification and reporting

Test immutable settings, no active-run change after editing environment, new-run application of approved values, run-folder uniqueness, offset correctness, JSONL validity, ordered concurrent events, secret redaction, mandatory traces at all log levels and clean stdout/stderr.

Report exact changed files, approval scope, tests actually executed and pending work. Documentation edits alone do not implement the logger or DI container. Installation of this skill must be reported separately from creation of its deliverable.
