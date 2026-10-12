# Live conversation tests

Not unit tests and not isolated: they are end-to-end checks that run the whole app. Scenarios that drive the real app (stdin/stdout protocol) against the real Claude API and grade
what the participants saw plus the trace events. They cost API calls and take minutes, so they are
not part of `uv run pytest`. They need `ANTHROPIC_API_KEY` (environment or `.env`).

## Run

```bash
uv run python tests/live/run.py --list                  # names and descriptions
uv run python tests/live/run.py dates_calendar          # one scenario
uv run python tests/live/run.py 'dates_*' -j 3          # glob, 3 in parallel
uv run python tests/live/run.py --all -j 4              # everything
uv run python tests/live/run.py --now 2026-10-12T12:00:00+02:00 ...   # clock (default)
```

The clock is frozen with `--now` (default Monday 2026-10-12 12:00 Europe/Madrid), so the known
agenda ends on Monday 2026-10-19 (`VISIT_HORIZON_DAYS=7`) and visits are 09:00-19:00.
The runner shortens the `<NO RESPONSE>` retries through the `NO_RESPONSE_*` environment variables
(`NO_RESPONSE_RETRY_WAIT_SECONDS`, `NO_RESPONSE_MAX_RETRIES`, `NO_RESPONSE_POLL_SECONDS`), so the
retry scenarios finish quickly; the retry timer still uses the real UTC clock, not `--now`.
Run each scenario at most twice per verification round; keep `-j` at 3 or 4.

## Results

| Mark | Meaning |
|---|---|
| `PASS` | check passed |
| `FAIL` | check failed: a regression (exit code 1) |
| `XFAIL` | check marked `known_issue` and still failing: the bug is documented and still present |
| `XPASS` | check marked `known_issue` but passing: the bug is fixed, remove its `known_issue` |
| `TIME!` | the app did not start or did not finish a message in time (exit code 1) |

## Files of each run

`tests/live/runs/<YYYYMMDD-HHMMSS>/<scenario>/` contains `out.txt` (what participants saw),
`traces/events.jsonl` and `traces/runtime.jsonl`, the copy of `work_orders.csv` used and the
stderr of the process. `runs/` is local output.

## Report and bottleneck analysis

```bash
uv run python tests/live/report.py runs/<timestamp>   # default: newest run
```

Writes `report/<scenario>.md` (the conversation with the system's decisions interleaved) and
`report/SUMMARY.md` (friction signals per scenario). See the `live-conversation-analysis` skill.

## Add a scenario

1. In `scenarios.py` append a `Scenario(name, description, steps, final_checks=...)` to
   `_SCENARIOS`. Steps are built with `tenant(text, *checks, wo=...)`, `handyman(...)` or
   `raw(line, ...)`; `to_proposal()` gives the base flow up to a proposal for the tenant.
2. Checks live in `checks.py` (`evidence`, `event`, `reply_has`, `reply_lacks_regex`,
   `slot_on`, ...); `final_checks` grade the whole run, step checks only what that step caused.
3. If the behaviour is wrong today, pass `known_issue="why"` to the check: it reports
   XFAIL until fixed, then XPASS; after two consecutive XPASS runs remove the `known_issue`.

## Scenarios

| Scenario | Area / point covered |
|---|---|
| `dates_calendar`, `dates_time_of_day`, `dates_range` | Date validation: non-existent dates, impossible times, past, far future, weekday mismatch, night hours, beyond horizon |
| `dates_valid_inside_horizon`, `dates_valid_last_day` | Valid interval recorded; last day of the horizon (2026-10-19) accepted |
| `ambiguity_sequence` | Vague requests: table inside horizon, "el viernes" linked to the table (points 1, 2, 3, 5) |
| `ambiguity_friday_at_ten` | "viernes a las 10" resolved without an am/pm quiz (point 4) |
| `ambiguity_day_14` | "el 14" after a vague request shows only the 14th (point 2) |
| `ambiguity_next_week_horizon_sentence` | "next week" states the horizon, 19th included in the table (point 5) |
| `confirm_*` (7 scenarios) | Confirmations: no booking on "sí" without proposal, "sí pero no", emoji, changed hour, full flow, stale yes, long handyman acceptance |
| `injection_*` (6 scenarios) | Prompt-injection guard: blocked, mixed, disguised, night hour is not an attack, legitimate wording, handyman |
| `priority_text_does_not_matter`, `priority_reverse_order` | Urgency preemption and no overlapping appointments |
| `format_rejections`, `format_no_response_sentinel` | Inbound format: malformed, unknown WO, empty, oversize; `<NO RESPONSE>` |
| `roles_clarification_does_not_swap_role` | Role routing after a clarification |
| `cancel_by_tenant`, `cancel_by_handyman_after_tenant_yes`, `correction_after_proposal` | Cancellation and correction of availability |
| `no_response_names_the_waiting_role` | `<NO RESPONSE>` reason names the right role |
| `alternatives_new_availability_is_recorded` | Round 2, point 9: new availability in `tenant_alternatives` |
| `handyman_notified_when_proposal_withdrawn` | Round 2, point 10 (and event `proposal_withdrawn`, point 12) |
| `weekday_names_are_correct_in_replies` | Round 2, point 11: correct weekday names |
| `hold_released_is_traced` | Round 2, point 12: event `hold_released` |
| `recompose_has_no_stale_years` | Round 2, point 7: no invented 2024/2025 examples |
