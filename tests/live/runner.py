"""Live conversation runner: drives the real CLI (real Claude API) and checks traces and output.

Each scenario starts one process with its own CSV copy and trace folder, feeds the scripted
lines to stdin one at a time, waits until the app finished handling each one (by watching the
trace, not by guessing sleeps) and evaluates the checks attached to that step.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[2]
DEFAULT_NOW = "2026-10-12T12:00:00+02:00"
STARTUP_TIMEOUT = 90
STEP_TIMEOUT = 150
SETTLE_SECONDS = 1.5

_HEADER = re.compile(r"^WOID:([^|]+)\|(ROLE|RESULT):(.*)$")


@dataclass(frozen=True)
class Block:
    """One protocol frame written to stdout."""

    work_order_id: str
    kind: str  # "message" or "terminal"
    label: str  # role for messages, result for terminal frames
    body: str


class StepView:
    """What a step produced: only the events, runtime events and output frames it caused."""

    def __init__(self, events: list[dict], runtime: list[dict], blocks: list[Block]) -> None:
        self.events = events
        self.runtime = runtime
        self.blocks = blocks

    def events_of(self, event_type: str) -> list[dict]:
        return [event for event in self.events if event["event_type"] == event_type]

    @property
    def messages(self) -> list[Block]:
        return [block for block in self.blocks if block.kind == "message"]

    @property
    def terminals(self) -> list[Block]:
        return [block for block in self.blocks if block.kind == "terminal"]


@dataclass(frozen=True)
class Check:
    description: str
    test: Callable[[StepView], bool]
    known_issue: str | None = None  # expected to fail today; reported as XFAIL / XPASS


@dataclass(frozen=True)
class Step:
    """One inbound line. ``wait`` is "delivered", "rejected" or a number of seconds."""

    line: str
    checks: tuple[Check, ...] = ()
    wait: str | float = "delivered"


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    steps: tuple[Step, ...]
    extra_rows: tuple[str, ...] = ()  # CSV rows appended to the copy of work_orders.csv
    final_checks: tuple[Check, ...] = ()


@dataclass
class CheckResult:
    step: str
    description: str
    status: str  # PASS FAIL XFAIL XPASS TIMEOUT
    known_issue: str | None = None


@dataclass
class ScenarioResult:
    scenario: Scenario
    folder: Path
    results: list[CheckResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(item.status in ("FAIL", "TIMEOUT") for item in self.results)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def parse_blocks(text: str) -> list[Block]:
    blocks: list[Block] = []
    header: tuple[str, str, str] | None = None
    body: list[str] = []

    def flush() -> None:
        if header is not None:
            work_order, kind, label = header
            blocks.append(
                Block(
                    work_order,
                    "message" if kind == "ROLE" else "terminal",
                    label,
                    "\n".join(body).strip(),
                )
            )

    for line in text.splitlines():
        match = _HEADER.match(line)
        if match:
            flush()
            header, body = (match.group(1), match.group(2), match.group(3)), []
        else:
            body.append(line)
    flush()
    return blocks


class LiveRun:
    """One running app process plus read access to everything it wrote."""

    def __init__(self, scenario: Scenario, folder: Path, now: str) -> None:
        self.scenario = scenario
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        rows = (REPO / "work_orders.csv").read_text(encoding="utf-8").rstrip("\n").split("\n")
        rows.extend(scenario.extra_rows)
        self.csv = folder / "work_orders.csv"
        self.csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
        self.traces = folder / "traces"
        self.out_path = folder / "out.txt"
        self.err_path = folder / "err.txt"
        env = {
            **os.environ,
            "TRACES_DIR": str(self.traces),
            # Shorten the NO RESPONSE retries so a scenario sees the whole cycle in seconds.
            "NO_RESPONSE_RETRY_WAIT_SECONDS": "1",
            "NO_RESPONSE_MAX_RETRIES": "1",
            "NO_RESPONSE_POLL_SECONDS": "0.5",
        }
        self._out = self.out_path.open("w", encoding="utf-8")
        self._err = self.err_path.open("w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "maintenance_agent", "--csv", str(self.csv), "--now", now],
            cwd=REPO,
            env=env,
            stdin=subprocess.PIPE,
            stdout=self._out,
            stderr=self._err,
            text=True,
        )

    def _run_dir(self) -> Path | None:
        runs = sorted((self.traces / "runs").glob("*")) if (self.traces / "runs").exists() else []
        return runs[0] if runs else None

    def events(self) -> list[dict]:
        run_dir = self._run_dir()
        return _read_jsonl(run_dir / "events.jsonl") if run_dir else []

    def runtime(self) -> list[dict]:
        run_dir = self._run_dir()
        return _read_jsonl(run_dir / "runtime.jsonl") if run_dir else []

    def blocks(self) -> list[Block]:
        if not self._out.closed:
            self._out.flush()
        return parse_blocks(self.out_path.read_text(encoding="utf-8"))

    def _count(self, event_type: str) -> int:
        return sum(1 for event in self.events() if event["event_type"] == event_type)

    def _rejections(self) -> int:
        return sum(1 for e in self.events() if e["event_type"] == "message_rejected") + sum(
            1 for e in self.runtime() if e["event_type"] == "message_rejected"
        )

    def _wait_for(self, predicate: Callable[[], bool], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            if self.proc.poll() is not None:
                return predicate()
            time.sleep(0.5)
        return False

    def wait_started(self) -> bool:
        return self._wait_for(lambda: self._count("work_orders_started") >= 1, STARTUP_TIMEOUT)

    def send(self, step: Step) -> tuple[StepView, bool]:
        before = (len(self.events()), len(self.runtime()), len(self.blocks()))
        delivered, rejected = self._count("order_transition_delivered"), self._rejections()
        assert self.proc.stdin is not None
        self.proc.stdin.write(step.line + "\n")
        self.proc.stdin.flush()
        if step.wait == "delivered":
            arrived = self._wait_for(
                lambda: self._count("order_transition_delivered") > delivered, STEP_TIMEOUT
            )
        elif step.wait == "rejected":
            arrived = self._wait_for(lambda: self._rejections() > rejected, 30)
        else:
            time.sleep(float(step.wait))
            arrived = True
        time.sleep(SETTLE_SECONDS)
        view = StepView(
            self.events()[before[0] :], self.runtime()[before[1] :], self.blocks()[before[2] :]
        )
        return view, arrived

    def finish(self) -> int:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        try:
            code = self.proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            code = -9
        self._out.close()
        self._err.close()
        return code

    def whole(self) -> StepView:
        return StepView(self.events(), self.runtime(), self.blocks())


def _grade(check: Check, view: StepView) -> str:
    try:
        passed = bool(check.test(view))
    except Exception:  # noqa: BLE001 - a broken check must not stop the run
        passed = False
    if check.known_issue:
        return "XPASS" if passed else "XFAIL"
    return "PASS" if passed else "FAIL"


def run_scenario(scenario: Scenario, base: Path, now: str = DEFAULT_NOW) -> ScenarioResult:
    folder = base / scenario.name
    shutil.rmtree(folder, ignore_errors=True)
    result = ScenarioResult(scenario, folder)
    run = LiveRun(scenario, folder, now)
    try:
        if not run.wait_started():
            result.results.append(CheckResult("startup", "app started", "TIMEOUT"))
            return result
        for number, step in enumerate(scenario.steps, start=1):
            view, arrived = run.send(step)
            label = f"#{number} {step.line[:70]!r}"
            if not arrived:
                result.results.append(CheckResult(label, "app finished the message", "TIMEOUT"))
            for check in step.checks:
                result.results.append(
                    CheckResult(label, check.description, _grade(check, view), check.known_issue)
                )
    finally:
        code = run.finish()
    whole = run.whole()
    for check in scenario.final_checks:
        result.results.append(
            CheckResult("final", check.description, _grade(check, whole), check.known_issue)
        )
    stderr = run.err_path.read_text(encoding="utf-8").strip()
    result.results.append(
        CheckResult(
            "process",
            "exit code 0 and empty stderr",
            "PASS" if code == 0 and not stderr else "FAIL",
        )
    )
    if stderr:
        result.notes.append(f"stderr: {stderr[:300]}")
    return result
