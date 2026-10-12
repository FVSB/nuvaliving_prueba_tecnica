# Language Recognition Contract

## Purpose

Define the boundary between the scheduling graph node and the injected language-recognition
adapter. It is internal: it does not change the CLI input or output protocol.

## Input

```python
async def recognize(description: str) -> LanguageRecognitionResult: ...
```

- `description` is the exact `WorkOrder.description` text.
- The recognizer must not read environment variables or access global dependencies.

## Output

```python
LanguageRecognitionResult(language_code: LanguageCode)
```

`language_code` must be exactly one of:

```text
es, en, fr, de, it, pt, nl, ca, ar, zh, ja, ko, undetermined
```

## Required behavior

- Empty, whitespace-only, numeric-only, unsupported, ambiguous, or malformed-provider results
  produce `undetermined`.
- No raw prompt, API key, model reasoning, or unvalidated provider text enters graph state, stdout,
  or normal stderr.
- The graph node invokes recognition once per workflow start and adds the validated result to state
  before the initialization node runs.
