# Data Model: Infer Work-Order Language

## `LanguageCode`

A pure-domain `StrEnum` of common ISO 639-1 codes:

| Language | Value |
|---|---|
| Spanish | `es` |
| English | `en` |
| French | `fr` |
| German | `de` |
| Italian | `it` |
| Portuguese | `pt` |
| Dutch | `nl` |
| Catalan | `ca` |
| Arabic | `ar` |
| Chinese | `zh` |
| Japanese | `ja` |
| Korean | `ko` |
| Indeterminate | `undetermined` |

Validation rules:

- Only these values may be retained as a language recognition result in this increment.
- The model adapter maps missing, malformed, unsupported, or ambiguous model output to
  `undetermined`; it never substitutes a default language.

## `LanguageRecognitionResult`

A frozen validated domain value with:

| Field | Type | Rules |
|---|---|---|
| `language_code` | `LanguageCode` | A common ISO 639-1 code or `undetermined`. |

The result contains no raw prompt, credential, or provider response.

## `SchedulingState`

A `TypedDict` state for the compiled scheduling graph:

| Field | Type | Rules |
|---|---|---|
| `work_order` | `WorkOrder` | Input for the run; includes the raw description. |
| `language_recognition` | `LanguageRecognitionResult` | Absent before `recognize_language`; required after it. |

State transition:

```text
initial(work_order) -> recognize_language -> state with language_recognition -> initialize_coordination
```

## `LanguageRecognizer` port

An asynchronous application-facing protocol:

```text
recognize(description: str) -> LanguageRecognitionResult
```

The graph node accepts this port by explicit dependency injection. An Anthropic-backed adapter
implements it in infrastructure; a fake implementation supports tests.
