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

## Pytest (focused)

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/unit/test_languages.py \
  tests/unit/test_language_recognition_node.py \
  tests/unit/test_language_prompt.py \
  tests/unit/test_anthropic_language_recognizer.py \
  tests/integration/test_scheduling_graph.py -v
```

Result: **20 passed in 2.18s**

| Test | Module | Status |
|---|---|---|
| test_configure_logging_defaults_to_quiet_root | tests/unit/test_bootstrap.py | passed |
| test_configure_logging_silences_third_party_loggers | tests/unit/test_bootstrap.py | passed |
| test_configure_logging_elevates_root_when_requested | tests/unit/test_bootstrap.py | passed |
| test_configure_logging_accepts_lowercase_level_names | tests/unit/test_bootstrap.py | passed |
| test_configure_logging_falls_back_to_warning_for_unknown_levels | tests/unit/test_bootstrap.py | passed |
| test_catalogue_contains_required_common_iso_codes | tests/unit/test_languages.py | passed |
| test_unknown_provider_value_becomes_undetermined | tests/unit/test_languages.py | passed |
| test_node_adds_validated_language_result_to_state | tests/unit/test_language_recognition_node.py | passed |
| test_node_preserves_undetermined_result | tests/unit/test_language_recognition_node.py | passed |
| test_prompt_is_english_and_lists_allowed_values | tests/unit/test_language_prompt.py | passed |
| test_recognizer_validates_provider_language_code | tests/unit/test_anthropic_language_recognizer.py | passed |
| test_recognizer_maps_invalid_provider_output_to_undetermined | tests/unit/test_anthropic_language_recognizer.py | passed |
| test_recognizer_skips_provider_for_blank_description | tests/unit/test_anthropic_language_recognizer.py | passed |
| test_graph_recognizes_language_before_initial_message | tests/integration/test_scheduling_graph.py | passed |
| test_graph_retains_undetermined_result | tests/integration/test_scheduling_graph.py | passed |
| test_graph_recognizes_english_before_initial_message | tests/integration/test_scheduling_graph.py | passed |
| test_coordinator_starts_each_work_order_then_reflects_live_message | tests/integration/test_async_coordination.py | passed |
| test_csv_reader_normalizes_all_rows_to_injected_timezone | tests/integration/test_async_coordination.py | passed |
| test_coordinator_logs_recognized_language_per_work_order | tests/integration/test_async_coordination.py | passed |
| test_coordinator_logs_inbound_dispatch_and_reflection | tests/integration/test_async_coordination.py | passed |

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

## Language-recognition logging

Logging is **silent by default** to keep the console clean. Operators opt in by exporting
`LOG_LEVEL=INFO` (or `DEBUG`). `bootstrap._configure_logging` configures the root logger from
`Settings.log_level` and pins `httpx`, `httpcore`, and `anthropic` to `WARNING` so provider
transport traces (e.g. `HTTP Request: POST https://api.anthropic.com/...`) never reach the
console. The stdout wire format emitted by `AsyncStdoutWriter` is never affected.

When `LOG_LEVEL=INFO`, every node transition emits one structured record to stderr using the
format `%(asctime)s %(levelname)s %(message)s`, with each message prefixed by `[<node>]` so the
operator sees which node produced it.

Example run for one Spanish work order plus one inbound tenant message:

```
2026-10-12 18:30:30,025 INFO [recognize_language] wo=WO-7 node=recognize_language language=es input_description='Hay una fuga de agua.' language 'es' recognized for the supplied description
2026-10-12 18:30:30,026 INFO [initialize_coordination] wo=WO-7 node=initialize_coordination direction=in
2026-10-12 18:30:30,026 INFO [initialize_coordination] wo=WO-7 node=initialize_coordination direction=out role=tenant body='Nueva orden de trabajo iniciada.'
2026-10-12 18:30:30,026 INFO [coordinator] wo=WO-7 node=reflect_inbound_message direction=in role=tenant body='Need help | urgent'
2026-10-12 18:30:30,027 INFO [reflect_inbound_message] wo=WO-7 node=reflect_inbound_message direction=out role=tenant body='Need help | urgent'
```

Every record carries the work-order id, the node name, and (for protocol payloads) the direction
(in/out) plus role and body. No prompt, credential, or model reasoning is included.