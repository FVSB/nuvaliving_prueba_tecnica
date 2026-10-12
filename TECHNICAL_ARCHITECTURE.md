# Technical Architecture Constitution — LangGraph

## Authority and Process

`BUSINESS_RULES.md` defines behavior and takes precedence for functional policy. This document
defines how the CLI Docker application is built. Before every code, configuration, documentation, or structural
change, the coding agent MUST show objective, affected files, architectural impact, preview,
alternatives, risks, tests, and ask: “¿Apruebas este cambio concreto?”. Approval covers only the
described scope. Approved architectural exceptions must be recorded in versioned files and
Engram when available.

## Architecture

The application is a CLI in Docker. Do not add API, web, database, Redis, email delivery, or new
services without demonstrated need and approval.

```text
src/maintenance_agent/
  __main__.py  bootstrap.py  config.py  dependencies.py
  domain/          # pure models, policies, scheduling
  application/     # coordinator, ports, lifecycle
  agents/scheduling/
    graph.py  state.py  nodes/  routers/
  prompts/         # typed reusable prompt builders
  infrastructure/  # CSV, CLI, Anthropic, JSONL, rendering
tests/{unit,integration,acceptance}/
docs/{decisions,graphs}/
```

Create only justified modules. Code, identifiers, comments, logs, and docstrings are English.
Use Python 3.12+, Pydantic v2 at validated boundaries, `TypedDict` where LangGraph reducers need
it, strict static typing, Ruff, and reproducible `uv` dependencies. Each significant graph node
has a focused file; `graph.py` only wires injected nodes and routes. Domain rules have no
LangGraph, Anthropic, CLI, or filesystem dependency.

## Startup-only Dependencies

`bootstrap.py` is the sole composition root. Once per process it builds validated Pydantic
Settings, run context, JSONL logger, trace writer, CSV adapter, CLI transport, Anthropic client,
in-memory schedule authority, `dependency-injector` container, and compiled graph. Resources are
explicitly injected and closed once. Nodes never read environment variables, create clients, or
query a global container.

Settings are read once through `pydantic-settings` from environment and optional `.env`; no
`load_dotenv()`, `os.getenv()`, import-time I/O, hot reload, or mutable global state. The approved
credential is `ANTHROPIC_API_KEY`; it is secret, omitted from logs, `.env.example` values, Git,
and Docker build context. Its absence fails only when an Anthropic node is enabled.

## Concurrency, State, and Consistency

Use one state and sequential event queue per work order, while allowing different orders to make
progress concurrently. Serialize complete stdout blocks and JSONL writes. Never hold the shared
schedule lock across LLM calls or human waits. Validate LLM structured output before use and
discard stale results against proposal/state version. Closing is idempotent within the process.

The schedule authority atomically checks and reserves semi-open `[start, end)` intervals. The
graph coordinates it but never embeds business policy. Do not promise recovery after process
crash without an approved persistence protocol.

## Observability and Graph Views

Create one run folder under `/app/traces/runs/` named with Madrid start timestamp, offset, and a
unique run ID. `manifest.jsonl`, `events.jsonl`, and `runtime.jsonl` are JSONL only; correlate by
run ID, sequence, work order, proposal version, and state version. Redact secrets and avoid model
private reasoning. No console handlers are allowed.

Every approved topology change receives editable Mermaid and, when local rendering is available,
PNG under `docs/graphs/`. The rendered image must correspond to the implemented graph; rendering
failure cannot block the evaluator.

## Verification and Maintenance

Test pure domain rules without I/O, isolated dependency injection, import-time safety, ordering,
schedule races, terminal idempotency, protocol framing, JSONL validity, secret redaction, Docker
execution, and graph rendering isolation. Distinguish fakes, Docker validation, and real
Anthropic access in reports. Keep `docs/configuration.md`, `.env.example`, decisions, tests, and
Engram synchronized after approved configuration or logging changes.
