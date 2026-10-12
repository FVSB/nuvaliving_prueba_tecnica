# Validation Results: Infer Work-Order Language

**Feature**: `003-infer-order-language`
**Branch**: `003-infer-order-language`
**Date**: 2026-10-12
**Scope**: T018 + T019 from `specs/003-infer-order-language/tasks.md`

## Ruff

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests
```

Result:

```
All checks passed!
```

## Pytest

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/unit/test_languages.py \
  tests/unit/test_language_recognition_node.py \
  tests/unit/test_language_prompt.py \
  tests/unit/test_anthropic_language_recognizer.py \
  tests/integration/test_scheduling_graph.py -v
```

Result: **11 passed in 1.98s**

Coverage includes domain validation, prompt construction, Anthropic adapter validation, and graph
integration for Spanish, English, and undetermined results. This is the focused suite listed in
`quickstart.md`.

## Graph topology vs. diagram

Compiled graph (`src/maintenance_agent/agents/scheduling/graph.py`):

```
START -> recognize_language -> initialize_coordination -> END
```

Mermaid source (`docs/graphs/003-language-inference-flow.mmd`):

```mermaid
flowchart LR
    START([START]) --> RECOGNIZE[recognize_language]
    RECOGNIZE --> INITIALIZE[initialize_coordination]
    INITIALIZE --> CONTINUE([existing coordination flow])
    RECOGNIZE --> STATE[(SchedulingState.language_recognition)]
```

The diagram documents the same node order; the `RECOGNIZE --> STATE` edge represents the
`SchedulingState.language_recognition` state update returned by `RecognizeLanguageNode`, not a graph
edge. Rendered PNG: `docs/graphs/003-language-inference-flow.png` (21226 bytes), generated locally
with `mmdc` driving the cached Playwright Chromium 1223.

## Real-provider smoke

Not executed in this validation run. Per `quickstart.md`, a real-provider smoke run requires a
developer-approved non-production `ANTHROPIC_API_KEY` and is reported separately from these
fake-provider focused tests.

## Run-scoped JSONL traces

The console stays clean: stdout contains only protocol blocks and stderr remains empty. Each run
creates `/app/traces/runs/<Madrid_start_with_offset>-<run_id>/` in Docker (or `traces/runs/` in a
local checkout), containing `manifest.jsonl`, `events.jsonl`, and `runtime.jsonl`.

The real CLI verification wrote a run with `run_id=b14c8583`. Its `events.jsonl` recorded Spanish
and English `language_recognized` events, node entry/exit events, tenant outbound messages, and a
final application-scoped `run_completed` event. Every record has a run id, monotonic sequence,
Madrid-offset timestamp, scope, work-order id (or `null` for application events), event type, and
errors omit exception messages.
