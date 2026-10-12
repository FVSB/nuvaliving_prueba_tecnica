"""Run the live conversation scenarios against the real app and the real Claude API.

    uv run python tests/live/run.py --list
    uv run python tests/live/run.py dates_calendar injection_attacks
    uv run python tests/live/run.py 'dates_*' -j 4
    uv run python tests/live/run.py --all -j 6

Each scenario writes out.txt (what participants saw), traces/ (events.jsonl, runtime.jsonl) and
work_orders.csv under tests/live/runs/<timestamp>/<scenario>/. They cost API calls and take
minutes: the app is given the time it needs per message, not a fixed sleep.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runner import DEFAULT_NOW, REPO, ScenarioResult, run_scenario  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402

RUNS = Path(__file__).resolve().parent / "runs"
MARK = {"PASS": "PASS ", "FAIL": "FAIL ", "XFAIL": "XFAIL", "XPASS": "XPASS", "TIMEOUT": "TIME!"}


def _has_api_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "ANTHROPIC_API_KEY" and value.strip().strip("\"'"):
                return True
    return False


def _select(patterns: list[str], everything: bool) -> list[str]:
    if everything or not patterns:
        return list(SCENARIOS) if everything else []
    names = [name for name in SCENARIOS if any(fnmatch.fnmatch(name, p) for p in patterns)]
    unknown = [p for p in patterns if not any(fnmatch.fnmatch(n, p) for n in SCENARIOS)]
    if unknown:
        raise SystemExit(f"No scenario matches: {', '.join(unknown)} (use --list)")
    return names


def _print(result: ScenarioResult) -> None:
    print(f"\n=== {result.scenario.name} - {result.scenario.description}")
    for item in result.results:
        extra = f"   [known issue: {item.known_issue}]" if item.known_issue else ""
        print(f"  {MARK[item.status]} {item.step}: {item.description}{extra}")
    for note in result.notes:
        print(f"  note: {note}")
    print(f"  files: {result.folder}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("scenarios", nargs="*", help="scenario names or glob patterns")
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    parser.add_argument("--all", action="store_true", help="run every scenario")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="scenarios run in parallel")
    parser.add_argument("--now", default=DEFAULT_NOW, help=f"frozen clock (default {DEFAULT_NOW})")
    args = parser.parse_args()

    if args.list:
        for name, scenario in SCENARIOS.items():
            print(f"{name:42} {scenario.description}")
        return 0
    names = _select(args.scenarios, args.all)
    if not names:
        parser.print_help()
        return 2
    if not _has_api_key():
        print("ANTHROPIC_API_KEY is not set (environment or .env): these tests call the real API.")
        return 2

    base = RUNS / time.strftime("%Y%m%d-%H%M%S")
    base.mkdir(parents=True, exist_ok=True)
    print(f"Running {len(names)} scenario(s), {args.jobs} at a time; files in {base}")
    failed = False
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_scenario, SCENARIOS[name], base, args.now) for name in names]
        results = []
        for future in futures:
            result = future.result()
            results.append(result)
            _print(result)
            failed = failed or result.failed

    counts: dict[str, int] = {}
    for result in results:
        for item in result.results:
            counts[item.status] = counts.get(item.status, 0) + 1
    print("\nSUMMARY " + "  ".join(f"{status}={count}" for status, count in sorted(counts.items())))
    print("XFAIL = known bug still present, XPASS = known bug fixed (remove its known_issue).")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
