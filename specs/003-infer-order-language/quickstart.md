# Quickstart: Verify Work-Order Language Recognition

## Preconditions

- Use Python 3.12 and the project environment managed by `uv`.
- Set `ANTHROPIC_API_KEY` only for a real-provider run. Tests use an injected fake recognizer and
  do not require a credential.

## Automated verification

Run the focused unit and integration tests planned for this feature:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/unit/test_languages.py \
  tests/unit/test_language_recognition_node.py \
  tests/unit/test_language_prompt.py \
  tests/unit/test_anthropic_language_recognizer.py \
  tests/integration/test_scheduling_graph.py
```

Expected cases:

1. A clearly Spanish description yields `es` before initial coordination.
2. A clearly English description yields `en` before initial coordination.
3. Empty, ambiguous, unsupported, or malformed classifier results yield `undetermined`.
4. The initial tenant notification still uses the established CLI framing and is emitted only after
   the recognition state update.

## Real-provider smoke check

With an explicit developer-approved non-production credential, launch the CLI with a fixture CSV
containing one clear Spanish and one clear English description. Inspect
`traces/runs/<run>/events.jsonl` locally, or `/app/traces/runs/<run>/events.jsonl` in Docker, for
the `language_recognized` records and their validated `detail.language_code` fields. Do not print
credentials, prompts, or model private reasoning to the terminal.
