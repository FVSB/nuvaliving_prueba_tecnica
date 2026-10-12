# Implementation Plan: Infer Work-Order Language

**Branch**: `003-infer-order-language` | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-infer-order-language/spec.md`

## Summary

Introduce the first compiled LangGraph scheduling pipeline. Its entry node receives each valid
`WorkOrder`, asks an explicitly injected language recognizer to classify `description` through an
English-only typed prompt, validates the response against a shared ISO 639-1 catalogue, and writes
the resulting code or `undetermined` value into typed graph state. Only after that state update
does the existing initial tenant notification run. An Anthropic-backed adapter remains behind a
narrow port; tests use fakes and never need a real credential.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: LangGraph (new); Anthropic Python SDK (new); Pydantic v2; dependency-injector  
**Storage**: Process-local compiled graph state; existing JSONL trace design remains authoritative  
**Testing**: pytest, pytest-asyncio, Ruff; fake recognizer unit/integration tests; separately reported real Anthropic smoke test  
**Target Platform**: Docker CLI on Linux  
**Project Type**: Single-process asynchronous CLI application  
**Performance Goals**: Process five to eight startup work orders without serializing independent order workflows; invoke recognition once per order start  
**Constraints**: `ANTHROPIC_API_KEY` is startup-only and redacted; no new service, database, or stdout/stderr diagnostics; model output is validated before state use; all new code, variables, comments, logs, docstrings, and prompts are English  
**Scale/Scope**: One first graph node, one language-recognition port/adapter, 12 common ISO 639-1 codes plus `undetermined`, and the existing initialization continuation

## Constitution Check

*GATE: Passed before Phase 0 research; re-checked after Phase 1 design.*

- [x] `docs/BUSINESS_RULES.md` and `docs/TECHNICAL_ARCHITECTURE.md` were read and no authority conflict exists.
- [x] Developer approval, affected files, preview, risks, alternatives, and validation are recorded in the feature specification, Decision 004, and this plan.
- [x] The design remains a Docker CLI and adds no service or business policy beyond the user-approved language-inference decision.
- [x] Node, typed state, injected dependencies, trace expectations, and graph topology are documented.
- [x] Work is on the dedicated `003-infer-order-language` feature branch; this repository uses numbered feature branches rather than the template's `feature/` prefix.

## Branch Workflow

**Working Branch**: `003-infer-order-language`  
**Integration Branch**: `develop`  
**Merge Gate**: Ruff plus focused unit/integration tests pass; graph diagram matches compiled topology; fake-provider tests cover Spanish, English, and indeterminate paths; optional real-provider smoke test is reported separately.

## Project Structure

### Documentation (this feature)

```text
specs/003-infer-order-language/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── language-recognition.md
└── tasks.md                  # Created later by /speckit-tasks

docs/
├── decisions/004-tenant-language-inference.md
└── graphs/003-language-inference-flow.mmd
```

### Source Code

```text
src/maintenance_agent/
├── agents/scheduling/
│   ├── graph.py                         # Wire graph only
│   ├── state.py                         # Typed scheduling state
│   └── nodes/
│       ├── recognize_language.py        # Focused entry node
│       └── initialize_coordination.py   # Existing continuation node
├── application/
│   └── language_recognition.py          # LanguageRecognizer port
├── domain/
│   └── languages.py                     # ISO catalogue and validated result
├── infrastructure/
│   └── anthropic_language_recognizer.py # SDK adapter
├── prompts/
│   └── language_recognition.py          # English typed prompt builder
├── dependencies.py                      # Explicit providers and graph wiring
└── bootstrap.py                          # Startup-only client composition

tests/
├── unit/
│   ├── test_languages.py
│   ├── test_language_recognition_node.py
│   └── test_language_prompt.py
└── integration/
    └── test_scheduling_graph.py
```

**Structure Decision**: Retain the existing single-project CLI. The domain owns closed language
vocabulary and result validation; application owns the port; infrastructure owns the Anthropic SDK
adapter; `prompts/` owns English prompt construction; and `agents/scheduling/` owns typed graph
state, nodes, and wiring.

## Implementation Sequence

1. Add reproducible `langgraph` and Anthropic SDK dependencies with `uv add`, retaining both
   `pyproject.toml` and `uv.lock`; document purpose and verification in `docs/development.md`.
2. Add the pure `LanguageCode`/`LanguageRecognitionResult` domain model and exhaustive unit tests.
3. Add the `LanguageRecognizer` port and an English prompt builder that exposes the allowed code
   vocabulary and instructs the provider to return `undetermined` under uncertainty.
4. Implement and validate the Anthropic adapter. It maps malformed, unsupported, blank, or
   ambiguous output to `undetermined`, and never logs prompts, credentials, or model reasoning.
5. Add `SchedulingState` and `RecognizeLanguageNode`; inject the recognizer and return only the
   validated state update.
6. Add `graph.py` to wire `START -> recognize_language -> initialize_coordination`; adapt the
   coordinator/container so each startup order runs through the compiled graph before any outbound
   message is written.
7. Update the Mermaid diagram to match the actual compiled graph and render a PNG when local
   rendering is available; update runtime/configuration documentation and JSONL trace handling if
   needed to record the validated result without sensitive content.
8. Run Ruff and the focused tests. Report fake-provider, local CLI, Docker, and real-provider
   results separately.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Model returns an unlisted or malformed value | Validate at the infrastructure boundary and use `undetermined`. |
| Model or credential failure affects startup | Enable the Anthropic adapter only through explicit startup injection; report failure according to approved policy rather than treating it as a tenant timeout. |
| Prompt/credential leaks into terminal output or traces | Keep prompts out of graph state; redact secrets; retain only the validated code. |
| The new graph delays or changes protocol framing | Preserve `AsyncStdoutWriter` as the sole formatter and test that initialization runs after recognition. |
| The diagram diverges from runtime wiring | Treat the Mermaid source and compiled graph integration test as one merge gate. |

## Complexity Tracking

No constitution violations require justification.
