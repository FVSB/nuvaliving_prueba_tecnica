# Configuration guide and per-run logs

## Status and sources

This guide accompanies TECHNICAL_ARCHITECTURE.md and BUSINESS_RULES.md. `Settings`, the container, and the per-run JSONL traces are implemented; keep this guide in sync with every approved change.

In the target repository, keep this information in `docs/configuration.md`, reference it from the README, and update it with every approved change. Business rules take precedence for functional policies; architecture defines the mechanisms.

## Where to find each thing

| Target location | Responsibility |
|---|---|
| `src/maintenance_agent/config.py` | Typed settings, validations, and constants |
| `src/maintenance_agent/bootstrap.py` | Only place that reads the environment, and initialization |
| `src/maintenance_agent/dependencies.py` | dependency-injector container and lifecycle |
| `src/maintenance_agent/infrastructure/trace_writer.py` | Run context and structured JSONL traces |
| `.env.example` | Only approved and implemented variables, no secrets |
| `docs/configuration.md` | Current catalog, constraints, and how changes are applied |
| `docs/decisions/` | Rationale and approval for relevant decisions |
| `.agents/skills/maintain-runtime-configuration/SKILL.md` | Maintenance procedure |

The paths listed reflect the current implementation; create additional modules only when justified.

## Initial catalog

| Parameter | Category | Environment / status | Constraint |
|---|---|---|---|
| Time zone | Approved startup-only setting | `LOCAL_TIMEZONE=Europe/Madrid` | Valid IANA zone; applies only to new runs |
| Slot suggestion grid | Approved startup-only setting | `SLOT_LOOKAHEAD_DAYS=7`, `SLOT_DAILY_START_HOUR=9`, `SLOT_DAILY_END_HOUR=19`, `SLOT_HOURS=2` | Presentation only; never evidence of availability; the window must contain at least one slot; the table is limited to the visit horizon (effective window = `VISIT_HORIZON_DAYS` + 1 days) |
| Prompt injection guard | Approved startup-only setting | `INJECTION_THRESHOLD=0.6` | `0 <= value < 1`; active only with `ANTHROPIC_API_KEY`; fails open on provider errors |
| Visit horizon | Approved startup-only setting | `VISIT_HORIZON_DAYS=7` | Integer > 0; calendar days from today; dates further ahead are rejected as `too_far_ahead`; the allowed visit hours are 09:00-19:00 (`SLOT_DAILY_START_HOUR`/`SLOT_DAILY_END_HOUR`). User decision: the horizon is not extended; the agent states how far it knows the schedule ("I only know availability up to Wednesday 2026-10-19…") and the slot table is limited to it |
| Maximum message length | Approved startup-only setting | `MAX_MESSAGE_LENGTH=2000` | Integer > 0; longer messages are rejected with a fixed reply before any model call |
| `<NO RESPONSE>` retries | Approved startup-only setting | `NO_RESPONSE_RETRY_WAIT_SECONDS=300`, `NO_RESPONSE_MAX_RETRIES=3`, `NO_RESPONSE_POLL_SECONDS=10` | Wait and poll: number > 0 (seconds); retries: integer >= 0 (0 closes at the first expiry). All have default values, so no `.env` is required. Measured with the real UTC clock, never with the business clock frozen by `--now`. See `docs/BUSINESS_RULES.md` |
| Visit duration | Binding business rule | Two-hour constant | Do not change the duration; DST is covered by the IANA database |
| Number of handymen | Binding business rule | Constant: one | Do not parameterize to change the contract |
| CSV | Binding business rule | `/app/work_orders.csv`, read-only | Keep the evaluation path |
| Logs/traces | Binding business rule | `TRACES_DIR=traces` locally; `/app/traces` in Docker, JSONL | Startup-only; one folder per run |
| Anthropic credential | Documented credential | `ANTHROPIC_API_KEY`, if the client needs it | Secret; do not log its value or commit `.env` |
| Language recognition model | Startup-only setting | `ANTHROPIC_LANGUAGE_MODEL=claude-haiku-5-5` | Non-empty name; applies at the next startup |
| Conversation model | Startup-only setting | `ANTHROPIC_CONVERSATION_MODEL=claude-haiku-5-5` | Non-empty name; applies at the next startup |
| Injection guard model | Startup-only setting | `ANTHROPIC_INJECTION_MODEL=claude-haiku-5-5` | Non-empty name; applies at the next startup; only with `ANTHROPIC_API_KEY` |
| Versioned business rules (JSON) | Startup-only setting | `BUSINESS_RULES_PATH=config/business_rules.json` (Docker: `/app/config/business_rules.json`, included in the image) | File is validated at startup; if it is invalid or a level of `Urgency` or a language is missing, the process does not start. Contains `urgency_rank`, `no_response_retries_enabled` (default `false`: a `<NO RESPONSE>` closes the order as `requires_review` with no reminders; `true` enables the `NO_RESPONSE_*` retries), and `messages` texts (es/en). Changes are reviewed in a PR and require a new image or a restart |
| CSV path | Startup-only setting (pending policy approval) | `WORK_ORDERS_CSV_PATH=/app/work_orders.csv`; the CLI `--csv` takes priority | Makes configurable a path this catalog marked as fixed for evaluation; requires explicit approval before use outside tests |
| Traces directory | Approved startup-only setting | `TRACES_DIR=traces` locally; Docker fixes `/app/traces` | Does not change an active run; do not log secrets |
| LLM concurrency | Technical | Ask before creating a variable | Do not block receiving other orders |
| Relative date reference | Open policy | Approve the policy, then ask whether it is an environment setting | `reported_at` does not imply "today" |
| Working hours | Undefined policy | Ask whether to add them and whether to use the environment | Do not invent time slots or availability |
| Timeout / clarification budget | Open policy | Approve the policy, then ask whether it is an environment setting | Human timeout only by marker, not by clock |

Do not assign variable names or arbitrary defaults to the candidates. After approval, record: name, type, default value, validation, consumer/provider, source, whether it is a secret, and whether a restart is required.

## How to find logs by run start time

Planned layout:

```text
/app/traces/runs/<Madrid_start_with_offset>-<unique_run_id>/
  manifest.jsonl
  events.jsonl
  runtime.jsonl
```

The evaluation command documented in `BUSINESS_RULES.md` mounts `./traces` from the host into `/app/traces`: on the host, look in `traces/runs/` and find the folder by start date/time. Keep one folder per run even if it lasts hours or days. The application creates the three JSONL paths at startup and does not install console handlers.

- `manifest.jsonl`: start/end, run ID, and the effective snapshot without secrets.
- `events.jsonl`: incoming messages, decisions, state changes, outgoing messages, and terminal results per order.
- `runtime.jsonl`: technical logs and sanitized errors.
- `outgoing_message` is written after the full block has been flushed to stdout, and records the body and recipient role actually sent. `terminal_result` is written after the terminal frame has been flushed to stdout.
- Unreadable CLI lines (without `|` or with an invalid role) are ignored and produce `malformed_input` and `message_rejected` (`protocol_mismatch`) in `runtime.jsonl`, with the reason, length, and the received line.
- Lines with a valid ID and role but an empty body, a body longer than `MAX_MESSAGE_LENGTH`, or an unknown ID get a fixed reply (es/en) and produce `message_rejected` (and `unknown_work_order` where applicable) in `events.jsonl`.
- Valid and rejected messages received for an order that is already completed are ignored; events that were queued when that order emitted its terminal result are not processed either.
- Search by `work_order_id` to reconstruct an order, and sort by `sequence` within the run; timestamps keep the real Madrid offset.
- The log time does not govern human timeouts or the business time reference.

## Changing configuration later

1. Review `BUSINESS_RULES.md`, the architecture, the current configuration, and the relevant Engram memory.
2. Propose the change and ask whether the parameter should be an environment setting or a constant.
3. For policies, first approve their functional meaning. Do not modify binding constants.
4. Obtain specific approval and preview the files and tests affected.
5. Update Settings, DI, the environment example, the catalog, decisions, tests, and the skill as applicable.
6. Apply the new environment **only at the next startup**. No hot reload and no mutation of active providers. In Docker, recreate the container with the updated environment when authorized; changing the host file does not modify the running process.
7. Verify the snapshot, a new run, the logger, and that an active run is unaffected, using isolated tests.
8. Save the verified result and paths in Engram, with keys separated by topic and without secrets.

Do not stop an evaluation or run with pending orders automatically to apply configuration. Record what was proposed, approved, implemented, and verified.

## Approved local time zone

`LOCAL_TIMEZONE` is read once at startup and defaults to `Europe/Madrid`. It must be an installed IANA identifier (for example, `Europe/Madrid`). The CSV reader normalizes `reported_at` to this zone while keeping the original instant, and rejects timestamps without an offset. Changing it requires restarting the process or container; it never modifies an active run.

## Anthropic models

`ANTHROPIC_LANGUAGE_MODEL` selects the language recognition model, and `ANTHROPIC_CONVERSATION_MODEL` selects the model that interprets and composes messages. Both variables default to `claude-haiku-5-5` and require a non-empty identifier. They are read at startup; each run manifest records the two effective models and never the credentials.

## Local CSV selection

For development, run `uv run maintenance-agent --csv ./work_orders.csv`. The argument is passed to the composition root and injected into the CSV adapter once. Without it, both local and Docker execution keep `/app/work_orders.csv`. No extra environment variable is introduced. The root production Dockerfile uses the same `uv.lock` and receives secrets with `--env-file` at runtime, never during the build.
