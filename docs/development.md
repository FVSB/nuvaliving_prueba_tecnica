# Development and delivery

## Recommended: local development, Docker delivery

Python 3.12+ and uv are required. From the repository root:

```bash
uv sync --frozen --all-groups
uv run maintenance-agent --csv ./work_orders.csv
```

No environment activation or development container is required. The two CSV work orders emit
startup messages immediately; then type `WO-001|tenant Hola | necesito ayuda` and press Enter.
The same commands work in Fish. The optional root `.env` is read once, with
`LOCAL_TIMEZONE=Europe/Madrid` as the default; never commit real credentials.

```bash
uv run pytest
uv run ruff check src tests
```

The CLI `--csv` argument is injected at bootstrap; without it the input is still the binding
`/app/work_orders.csv`. Application nodes remain independent from paths and environment reads.
Malformed CLI lines are ignored and recorded with their submitted text in the current run's
`runtime.jsonl`. EOF ends input normally.

### Reproducible clock (`--now`)

`--now <ISO timestamp with offset>` freezes the business clock for the whole process, so relative
dates ("tomorrow", "next week") and past-date checks give the same result on every run:

```bash
uv run maintenance-agent --csv ./work_orders.csv --now 2026-10-12T12:00:00+02:00
```

The offset is mandatory; a naive or invalid timestamp is rejected by argparse. The clock does not
advance during the run. The manifest records a `clock_frozen` event. Without the flag the real
Madrid clock is used. Tests inject the clock directly through `NegotiationWorkflow(clock=...)`.

## Docker delivery

The root Dockerfile is separate from the optional Dev Container and installs the application from
the same Python lockfile, without development tools, workspace agents, indexes or secrets.

```bash
mkdir -p traces
docker build -t agent .
docker run --rm --env-file .env -i \
  -v "$(pwd)/work_orders.csv:/app/work_orders.csv:ro" \
  -v "$(pwd)/traces:/app/traces" \
  agent
```

The evaluator run was verified on 2026-10-12: the image built, and the container exited
successfully with empty stderr. With Anthropic configured, startup recognized both English and
Spanish work orders; exact `<NO RESPONSE>` inputs produced one `requires_review` result per order.
Captured input, output, and traces are in [`examples/docker-run/`](../examples/docker-run/).
This smoke run checks Docker startup, protocol, and timeout behavior. It does not cover a
successful scheduled negotiation inside Docker. The local suite passed 357 tests on this date.

## Optional Dev Container

The following configuration remains available but is not needed for local development.
The previous Dev Container build did not finish: the base Yarn apt signing issue was fixed, but
its inherited PATH configuration also blocked startup. Do not assume it is operational just because
the standalone application Dockerfile builds.


## Start and test

1. Start Docker Desktop with WSL integration and open this repository in VS Code.
2. Select **Dev Containers: Rebuild and Reopen in Container**.
3. From the repository terminal run `uv run maintenance-agent`.
4. Startup emits one handyman notification per CSV row. Send, for example,
   `WO-001|tenant Hola | necesito ayuda`, followed by Enter.
5. Run `uv run pytest` and `uv run ruff check src tests` for checks.

The root `work_orders.csv` is the supplied development example. It is mounted read-only at
`/app/work_orders.csv`. Edit it from the workspace and restart the CLI to reload it. Host `traces/`
is mounted at `/app/traces`. Every process run writes JSONL files below
`/app/traces/runs/<Madrid_start_with_offset>-<run_id>/`.
An optional workspace `.env` is read by the application at startup, not copied into the image.
Use `.env.example` with `LOCAL_TIMEZONE=Europe/Madrid` and keep real credentials out of Git.

## Shared files versus persistent tools

The **entire workspace**, including hidden files, is bind-mounted at its original absolute host
path. This intentionally preserves the existing `.codex/config.toml` instruction-file paths.
`.agents/skills/`, `AGENTS.md`, `.specify/`, `specs/`, `.codex/`, `.codegraph/`, and the application
source are the same files on both sides, not copied snapshots.

Codex/Claude homes, Go tools, and container Python environments use named volumes. The container's
Python environment is separate from the host `.venv`. Installed project Node tools are regenerated
with `npm ci`; do not run host and container installs on that folder simultaneously.

Engram is configured to use workspace `.engram-data/` to retain the existing project data; the old
named Engram volume is left intact, not deleted or silently imported. Do not run competing Engram
servers against the same SQLite store. Authenticate the agents inside the container, then run
`bash .devcontainer/setup-agents.sh` once to configure integrations/hooks. Existing host agent
sessions, global plugins and global skills are **not** automatically migrated. Project skills are
already shared; promote a needed global skill into `.agents/skills/` deliberately without secrets.

CodeGraph's installed CLI is registered for Codex and Claude. Its existing index stays shared;
no automatic `init`, deletion or unlock is performed. Do not run host and container watchers on
that database simultaneously. If an index/daemon reports a stale host process, stop that process
and inspect index status before deciding whether sync/unlock is necessary.

## Installation registry

| What | Source of truth | Reinstallation |
|---|---|---|
| Python 3.12 base | `.devcontainer/Dockerfile` | Rebuild |
| fish, timezone data | `.devcontainer/apt-packages.txt` | Rebuild |
| uv 0.9.24 | `.devcontainer/requirements-tools.txt` | Rebuild |
| Codex 0.162.1, CodeGraph 0.9.5 | `.devcontainer/package.json` + lock | Creation/rebuild |
| Engram v3.3.2 | `.devcontainer/go-tools.txt` | Creation/rebuild |
| Node 22, Go 1.24, Claude Code | Features + `devcontainer-lock.json` | Rebuild |
| Application and Python tests | `pyproject.toml` + `uv.lock` | Creation and every start |
| Project skills/conventions | `.agents/skills/`, `AGENTS.md` | Workspace bind mount |

For a new Python dependency use `uv add` or `uv add --dev`. For a CLI or OS tool, edit the relevant
manifest above and rebuild. An unrecorded `pip`, `npm -g`, or `apt install` is temporary and is not
reproducible delivery. Lifecycle scripts can be rerun; they do not auto-login or copy secrets.
Pins constrain direct dependencies; the base image tag, Debian package repositories and Go
transitive modules are not a byte-for-byte/offline image lock.

## Verification status

JSON/TOML parsing, shell syntax, lock consistency and the existing Python tests are checked on the
host. Docker build and runtime checks require a running Docker daemon; they must be reported
separately and are not implied by passing host tests.

## CLI bootstrap outside VS Code

The validation run uses a pinned, temporary host CLI (not an unregistered global install):

```bash
npx --yes @devcontainers/cli@0.80.0 up --workspace-folder "$PWD"
```

The lifecycle setup consumes the versioned manifests above. This CLI is only a host bootstrap tool;
VS Code supplies its own Dev Containers CLI.

## Language-recognition dependencies

`langgraph` compiles the scheduling pipeline and `anthropic` supplies the optional, injected
language-recognition adapter. Install or update them only with `uv add langgraph anthropic`, which
updates both `pyproject.toml` and `uv.lock`. Focused tests use a static recognizer and do not
require `ANTHROPIC_API_KEY`; a configured key selects the Anthropic adapter at startup.

## Prompt-injection guard

With `ANTHROPIC_API_KEY` set, the graph routes every inbound participant message through the
`injection_guard` node before `negotiation_transition` (`<NO RESPONSE>` and empty bodies skip it).
Up to three structured calls decide the outcome: whole message, the extracted suspect fragment
alone, and the message with that fragment removed by deterministic code. `INJECTION_THRESHOLD`
(default `0.6`, strictly-greater-than) is compared with the model's self-reported
`probability_yes`; the Anthropic API exposes no token log-probabilities. Outcomes recorded as
`injection_guard_screened` in `events.jsonl`: `pass`, `pass_cleaned` (only the cleaned body
continues) or `block` (the sender gets a fixed localized notice plus the last message sent to that
role, and the workflow never sees the text). Provider errors fail open and are written to
`runtime.jsonl` as `injection_guard_error`. Without an API key, or when tests inject a conversation
handler without a guard, the node is not built. The guard calls disable extended thinking because
a `thinking` block consumes the small `max_tokens` budget and leaves no JSON.

## Date and input validation

`domain/date_validation.py` is a pure tool (`validate_interval`, `validate_date_text`) that checks
every interval extracted from a message against the injected clock, `LOCAL_TIMEZONE`, the visit
hours (`SLOT_DAILY_START_HOUR`-`SLOT_DAILY_END_HOUR`, default 09-19) and `VISIT_HORIZON_DAYS`
(default 7). Failures return a `DateCheck` with a `DateErrorCode` and a short English reason; the
sender is asked again and the trace records `availability_rejected`. Inbound input is checked first:
unknown work order, empty body, or more than `MAX_MESSAGE_LENGTH` characters (default 2000) is
rejected with a fixed reply before the guard or any LLM. Order: deterministic checks, then the
injection guard, then LLM stages. Tests use `--now` or an injected clock and fakes; see
`specs/006-validate-date-tool/`.
Input rejections are fixed Spanish/English replies (`application/rejections.py`) for `empty_body`,
`too_long` and `unknown_work_order`; events `message_rejected` and `unknown_work_order` go to
`events.jsonl`. Unreadable lines (no `|`, invalid role) stay silent and are traced in
`runtime.jsonl` as `malformed_input` plus `message_rejected` with `protocol_mismatch`. Date
rejections come from `reject_invalid_availability` and the slot table is capped to the horizon.
Exact texts: `specs/006-validate-date-tool/spec.md`.

## Live conversation tests

Scenarios against the real API (not part of `pytest`) live in `integration_test/`; see
[`integration_test/README.md`](../integration_test/README.md) for how to run them, what
PASS/FAIL/XFAIL/XPASS mean and how to add one.

## Run traces

The CLI never writes logs to the console: stdout remains the protocol stream and stderr remains
empty. Each new local process creates exactly one folder under `TRACES_DIR` (default `traces/`);
the Docker image fixes it to `/app/traces` for the evaluator mount:

```text
traces/runs/<Madrid_start_with_offset>-<run_id>/
  manifest.jsonl
  events.jsonl
  runtime.jsonl
```

`manifest.jsonl` records lifecycle and the startup snapshot without credentials. `events.jsonl`
records every functional transition with `run_id`, `sequence`, timestamp with Madrid offset,
`work_order_id`, event type, and structured detail. `runtime.jsonl` contains sanitized technical
errors. To inspect a run after Docker execution:

```bash
latest=$(ls -dt traces/runs/* | head -1)
cat "$latest/events.jsonl"
```

Set `TRACES_DIR` before startup to override the local path; changing it does not affect an active
run.

When the LLM slot-suggestion path fails, `slot_suggestion_attempt` events carry a `diagnostic`
field with the failure reason (`truncated at max_tokens`, `schema mismatch [...]`, block types,
and a 200-character excerpt of the reply). The diagnostic is for traces only and is never fed back
into the next prompt; `slot_suggestion_feedback` still holds the sanitized one-line feedback.
