# Traces, execution examples and tests

## Traces

Each execution creates `/app/traces/runs/<timestamp>-<run_id>/` (on the host, `traces/runs/...`):

- `manifest.jsonl`: execution start, finish, and context.
- `events.jsonl`: incoming and outgoing messages, evidence, state changes, and decisions.
- `runtime.jsonl`: technical incidents and provider errors. These incidents are not a participant's silence.

Each event in `events.jsonl` contains `timestamp`, `run_id`, `sequence`, `work_order_id`, `event_type`, and `detail`. To reconstruct an order's conversation, filter `events.jsonl` by `work_order_id` and follow the `sequence` field.

## Complete run example (versioned)

A live run with the repository CSV and Anthropic: [`examples/complete-run/runs/20261012T170800+02:00-657314e2/`](../examples/complete-run/runs/20261012T170800+02:00-657314e2/). It includes the CSV, the JSONL traces, and a `conversation.txt` derived from the traces, with `IN`/`OUT` labels.

| Work order | Outcome | Detail |
|---|---|---|
| WO-001 | `scheduled` | 2026-10-13, 16:00–18:00, Madrid time; both participants explicitly accepted. |
| WO-002 | `requires_review` | The tenant sent the exact `<NO RESPONSE>` sentinel. With `no_response_retries_enabled=false` (default), the sentinel closes the order immediately. |

The run was started in the background with `uv run --no-sync maintenance-agent --csv ./examples/work_orders.csv` and closed through stdin EOF after both results. The initial messages were emitted for both orders before any participant replied.

Offline full-silence example: [`examples/complete-run/runs/20261012T233621+02:00-c72baec0/`](../examples/complete-run/runs/20261012T233621+02:00-c72baec0/). Both orders receive `<NO RESPONSE>` and end as `requires_review`.

## Docker run (smoke test)

[`examples/docker-run/`](../examples/docker-run/) contains the input, output, and JSONL traces of a container run. On 2026-10-12, `docker build -t agent .` completed successfully and the run exited with success and empty stderr. With Anthropic configured, it recognized the English and Spanish order descriptions; then both inputs timed out and produced exactly one `requires_review` result each.

This confirms startup, the protocol, and trace behavior, but it does **not** run a negotiation that ends in a scheduled visit inside Docker.

## Tests

The test suite is split by how much of the application each test exercises.

**Unit tests** (`tests/unit`) exercise focused rules and components with no live Anthropic calls. They cover interval and date validation, schedule conflicts and urgency, consent interpretation, input parsing, language settings, trace formatting, prompt-injection guard decisions, and deterministic slot tables. For example, schedule-authority tests check that overlapping concurrent reservations have one winner; guard tests check pass, clean, and block outcomes; date tests check invalid dates, hours, and horizon edges.

**Application integration tests** (`tests/integration`) connect the workflow, graph, coordinator, schedule authority, and transport, using controlled fakes wherever external model calls would otherwise be needed. They cover complete negotiation turns, concurrent orders, displacement and notices to displaced tenants, reversals, cancellation, input rejection, guard routing, and trace events.

**Acceptance tests** (`tests/acceptance`) exercise the CLI-facing behavior: startup messages, protocol framing, final results, and replies to vague dates.

Run the local suite with:

```bash
uv run pytest
```

### Live conversation evaluator

The [live conversation evaluator](../tests/live/README.md) runs the real CLI against Anthropic. It sends scripted tenant and handyman messages through stdin and checks both the replies and the JSONL traces. It covers date and ambiguity handling, agreement, prompt injection, priority, rejections, and availability changes. Because it makes live API calls, it costs more and takes longer than the local suite.

```bash
uv run python tests/live/run.py --list
uv run python tests/live/run.py dates_calendar
uv run python tests/live/run.py --all -j 4
```

Scenarios use a frozen business clock so date outcomes are reproducible. The runner's timeouts only detect a stuck test process; they do not simulate a participant's `<NO RESPONSE>` message.

Development dependencies and test configuration are defined in [pyproject.toml](../pyproject.toml).
