---
name: live-conversation-analysis
description: Run the live scripted conversation scenarios against the real Claude API, turn each run into markdown transcripts and find conversation bottlenecks (rejected drafts, fallbacks, invalid dates, misunderstood inconsistencies). Use when verifying scheduling behaviour end to end or hunting regressions in how the agent talks; not for unit tests.
---

# Live conversation analysis

Scenarios in `tests/live/` send fixed stdin lines (deterministic inputs) to the real app and
real Claude API, so replies vary but the script does not. They cost API calls: run each scenario
at most twice per round and keep `-j` at 3 or 4.

## Steps

1. Run: `uv run python tests/live/run.py --all -j 4 > <scratch>/suite.txt` (or a glob such
   as `'ambiguity_*'`). Put long runs in the background; do not detect the end with `pgrep -f`
   on the command text (it matches itself). Wait for the `SUMMARY PASS=…` line instead.
2. Report: `uv run python tests/live/report.py tests/live/runs/<timestamp>`. It writes
   `report/<scenario>.md` (conversation plus system decisions) and `report/SUMMARY.md`
   (friction signals per scenario, worst first).
3. Analyse in this order:
   - `TIME!`, `FAIL`, `XPASS` lines in `suite.txt` (XPASS: remove the check's `known_issue`).
   - `SUMMARY.md` hot spots; open the transcripts of the top scenarios.
   - Look for the agent re-asking for data already given, contradicting an earlier turn, replying
     in the wrong language or register, or looping on clarifications.
4. Write findings as: scenario, step, observed vs expected, suspected file. Count rates over
   several runs before claiming "always" or "never".

## Notes

- Add a scenario or check as described in `tests/live/README.md`.
- Add new friction signals to `SIGNALS` in `tests/live/report.py`.
- `tests/live/runs/` is local output; do not commit it.
