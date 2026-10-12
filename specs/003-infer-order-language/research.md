# Research: Infer Work-Order Language

## Decision: Use an injected Anthropic classifier behind a narrow application port

**Rationale**: The feature explicitly requires an English prompt and must infer language from
free-form descriptions. The existing architecture already approves `ANTHROPIC_API_KEY` as a
startup-only secret and requires LLM output to be validated evidence rather than business-policy
authority. A small `LanguageRecognizer` port lets the graph node depend on a typed result instead
of an SDK and allows deterministic fakes in tests.

**Alternatives considered**:

- Keyword or character heuristics: rejected because they cannot reliably cover the requested
  common-language catalogue or mixed descriptions.
- A new hosted language-detection service: rejected because it would add an unapproved service.
- Passing raw model output through the graph: rejected because the vocabulary and indeterminate
  behavior must be validated deterministically.

## Decision: Use ISO 639-1 two-letter codes plus one explicit `undetermined` value

**Rationale**: The approved feature specification adopts ISO 639-1 and requires a common-code
catalogue. A `StrEnum` with a separate `UNDETERMINED` member gives the domain a closed,
serializable vocabulary and makes unknown/ambiguous output safe.

**Alternatives considered**:

- ISO 639-3: rejected because it is less concise and exceeds the stated feature scope.
- Arbitrary strings from the model: rejected because they are not safely usable by later nodes.
- Defaulting to Spanish or English: rejected by FR-005 and FR-006.

## Decision: Make language recognition the graph entry node and preserve raw state separately

**Rationale**: LangGraph guidance recommends graph nodes return state updates and retain raw
values in state rather than prompt text. The graph starts at `recognize_language`, stores a
validated recognition result, then invokes the existing initialization behavior. This makes the
new topology observable and keeps later nodes from reinterpreting the description.

**Alternatives considered**:

- Detect language inside `InitializeCoordinationNode`: rejected because it mixes orchestration,
  model interaction, and notification creation in one node.
- Detect language during CSV parsing: rejected because parsing is an infrastructure concern and
  should not embed model behavior.
- Run recognition after the first notification: rejected because it violates FR-001.

## Decision: Keep prompt text in a typed English-only builder

**Rationale**: A focused `prompts/language_recognition.py` module provides a reusable prompt
builder without placing formatted prompt strings in state. It presents the description, allowed
codes, and instruction to return `undetermined` when confidence is insufficient.

**Alternatives considered**:

- Inline prompt in the node: rejected because it obscures prompt review and reuse.
- Prompt text in configuration: rejected because configuration is startup-only and the prompt is
  versioned application behavior, not runtime configuration.

## Sources

- [LangGraph workflow design guidance](https://docs.langchain.com/oss/javascript/langgraph/thinking-in-langgraph): nodes return state updates; keep raw values in state and format prompts in nodes.
- `docs/BUSINESS_RULES.md`: tenant-language inference is approved only through an explicit documented decision and tenant messaging remains Spanish or English.
- `docs/TECHNICAL_ARCHITECTURE.md`: LangGraph nodes use typed state and injected dependencies; LLM output must be validated before use.
