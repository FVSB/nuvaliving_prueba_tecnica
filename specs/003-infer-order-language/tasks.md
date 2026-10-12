# Tasks: Infer Work-Order Language

**Input**: Design documents from `/specs/003-infer-order-language/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/language-recognition.md, quickstart.md

**Tests**: Required by the feature specification and technical architecture.

## Phase 1: Setup

- [x] T001 Add reproducible `langgraph` and `anthropic` dependencies in pyproject.toml and uv.lock.
- [x] T002 [P] Add the language-recognition dependency purpose and verification steps in docs/development.md.

## Phase 2: Foundational

- [x] T003 Create ISO 639-1 language vocabulary and validated recognition result in src/maintenance_agent/domain/languages.py.
- [x] T004 [P] Create the injected LanguageRecognizer protocol in src/maintenance_agent/application/language_recognition.py.
- [x] T005 [P] Create the English-only prompt builder in src/maintenance_agent/prompts/language_recognition.py.
- [x] T006 Create typed LangGraph state in src/maintenance_agent/agents/scheduling/state.py.

## Phase 3: User Story 1 - Identify the language of a work order (Priority: P1) 🎯 MVP

**Goal**: Classify the description and store a validated ISO 639-1 code before initialization.

**Independent Test**: A fake recognizer makes Spanish and English work orders yield `es` and `en` in graph state before the initialization node emits its message.

- [x] T007 [P] [US1] Add domain vocabulary tests in tests/unit/test_languages.py.
- [x] T008 [P] [US1] Add prompt-builder tests in tests/unit/test_language_prompt.py.
- [x] T009 [P] [US1] Add recognition-node tests using a fake recognizer in tests/unit/test_language_recognition_node.py.
- [x] T010 [US1] Implement RecognizeLanguageNode in src/maintenance_agent/agents/scheduling/nodes/recognize_language.py.
- [x] T011 [US1] Implement graph wiring `START -> recognize_language -> initialize_coordination` in src/maintenance_agent/agents/scheduling/graph.py.
- [x] T012 [US1] Add injected Anthropic recognizer adapter in src/maintenance_agent/infrastructure/anthropic_language_recognizer.py.
- [x] T013 [US1] Wire the provider, node, and compiled graph through src/maintenance_agent/dependencies.py and src/maintenance_agent/application/coordinator.py.
- [x] T014 [US1] Add graph integration tests for Spanish and English descriptions in tests/integration/test_scheduling_graph.py.

## Phase 4: User Story 2 - Preserve uncertainty safely (Priority: P2)

**Goal**: Return `undetermined` for blank, ambiguous, unsupported, or malformed provider output.

**Independent Test**: Fake recognizer and adapter cases never turn uncertain input into a guessed ISO code.

- [x] T015 [P] [US2] Add indeterminate and malformed-output tests in tests/unit/test_languages.py and tests/unit/test_language_recognition_node.py.
- [x] T016 [US2] Map unsafe provider output to `undetermined` in src/maintenance_agent/infrastructure/anthropic_language_recognizer.py.
- [x] T017 [US2] Extend graph integration coverage for an undetermined result in tests/integration/test_scheduling_graph.py.

## Phase 5: Polish & Cross-Cutting Concerns

- [x] T018 Update docs/graphs/003-language-inference-flow.mmd to match the compiled graph and render a PNG when Mermaid tooling is available.
- [x] T019 Run Ruff and the focused test suite from specs/003-infer-order-language/quickstart.md; record actual validation results in the feature artifacts.

## Dependencies & Execution Order

- T001 blocks T011–T014 because graph and SDK imports require installed dependencies.
- T003–T006 form the foundation; T010 depends on T003, T004, and T006.
- T011 depends on T010; T013 depends on T011 and T012; T014 depends on T013.
- T015–T017 complete the safety story after the main recognition path is present.
- T018–T019 finish after both stories.

## Parallel Opportunities

- T002, T004, and T005 may proceed independently once T001 is complete.
- T007–T009 can be written in parallel after their respective contracts exist.
- T015 can proceed alongside the final main-path integration work.

## Implementation Strategy

Deliver the closed vocabulary and fake-tested graph path first. Then add the Anthropic adapter,
where invalid or uncertain output becomes `undetermined`. Preserve the existing CLI formatter and
initialization behavior; only the new graph orchestration determines when it runs.
