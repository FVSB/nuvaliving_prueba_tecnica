#!/usr/bin/env python3
"""Reproducible Docker validation: 8 work orders, urgency preemption and renegotiation.

Starts the agent exactly as the take-home prescribes (``docker run -i`` with the CSV mounted
read-only), plays the tenant and handyman of every work order with rule-based personas, and
then calls ``metrics.py`` on the produced traces.

    python validation/priority-renegotiation/run.py            # build image, run, metrics
    python validation/priority-renegotiation/run.py --no-build --out /tmp/val

Requires Docker and ``ANTHROPIC_API_KEY`` in ``.env`` at the repository root. Dates are relative
to the day of the run (D+1, D+2, D+3), so the scenario stays inside the 7-day horizon.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HEADER = re.compile(r"^WOID:([^|]+)\|(ROLE|RESULT):(.*)$")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
TIME = re.compile(r"\b(\d{2}:\d{2})\b")
ALL_WOS = [f"WO-{n:03d}" for n in range(1, 9)]

SCHEDULED = re.compile(
    r"programada|scheduled visit|reminder confirming|confirmation of your scheduled", re.I
)
NOWAIT = re.compile(
    r"no necesita responder|no es necesario que responda|cannot advance|no puede avanzar|"
    r"nothing (more )?to (reply|do)|need to reply",
    re.I,
)
DISPLACED = re.compile(r"displaced|reasignada|desplazad|higher[- ]priority|mayor prioridad", re.I)
CHANGE = re.compile(
    r"differs|distinta|diferente|different from|new (time )?interval|nuevo intervalo|"
    r"es correcto|is correct|cambio en su disponibilidad|change in your availability",
    re.I,
)
OPTIONS = re.compile(r"cuál|which|elija|pick|choose|indique la fecha|responda indicando", re.I)
CONFIRM_LIST = re.compile(r"confirm", re.I)
ASKS_DECISION = re.compile(r"acepta|rechaza|accept|reject|sí o (un )?no|yes or no|\?", re.I)


@dataclass
class Persona:
    """Scripted behaviour of one participant of one work order."""

    stages: list[str] = field(default_factory=list)  # availability statements, used in order
    windows: list[tuple[str, str, str]] = field(default_factory=list)  # (date, start, end) accepted
    rejects: list[tuple[str, str, str]] = field(default_factory=list)  # slots to decline once
    yes: str = "yes"
    idx: int = 0

    def next_stage(self) -> str:
        text = self.stages[min(self.idx, len(self.stages) - 1)]
        self.idx += 1
        return text


def build_personas(today: date) -> dict[tuple[str, str], Persona]:
    d1, d2, d3 = (str(today + timedelta(days=n)) for n in (1, 2, 3))
    w = lambda d, s, e: (d, s, e)  # noqa: E731
    return {
        # Critical, EN: wants the slot that Low WO-003 holds tentatively.
        ("WO-001", "tenant"): Persona([f"I am available on {d1} from 10:00 to 12:00."], yes="yes"),
        ("WO-001", "handyman"): Persona(windows=[w(d1, "10:00", "12:00")], yes="sí"),
        # Critical, ES: wants the slot that Medium WO-004 holds tentatively.
        ("WO-007", "tenant"): Persona([f"Estoy disponible el {d1} de 12:00 a 14:00."], yes="sí"),
        ("WO-007", "handyman"): Persona(windows=[w(d1, "12:00", "14:00")], yes="sí"),
        # High, ES: vague first reply, then an explicit slot from the suggestion table.
        ("WO-002", "tenant"): Persona(
            ["Puedo pasado mañana por la mañana", f"Me viene bien el {d3} de 09:00 a 11:00."],
            yes="sí",
        ),
        ("WO-002", "handyman"): Persona(windows=[w(d3, "09:00", "11:00")], yes="sí"),
        # Low, EN: holds d1 10-12, is displaced, renegotiates.
        ("WO-003", "tenant"): Persona(
            [
                f"I'm available on {d1} from 10:00 to 12:00.",
                f"I can do {d1} from 10:00 to 14:00, or {d2} from 16:00 to 18:00.",
                f"I'm available on {d2} from 16:00 to 18:00.",
            ],
            yes="yes",
        ),
        ("WO-003", "handyman"): Persona(
            [f"Puedo el {d2} de 16:00 a 18:00."],
            [w(d1, "10:00", "12:00"), w(d2, "16:00", "18:00")],
            yes="sí",
        ),
        # Medium, ES: holds d1 12-14, is displaced, handyman declines the next offer, renegotiates.
        ("WO-004", "tenant"): Persona(
            [
                f"Estoy disponible el {d1} de 12:00 a 14:00.",
                f"Puedo el {d2} de 10:00 a 12:00.",
                f"Estoy disponible el {d2} de 10:00 a 12:00 y el {d3} de 10:00 a 12:00.",
                f"Estoy disponible el {d3} de 11:00 a 13:00.",
            ],
            yes="sí",
        ),
        ("WO-004", "handyman"): Persona(
            [
                f"Puedo el {d2} de 12:00 a 14:00 y el {d3} de 10:00 a 12:00.",
                f"Puedo el {d3} de 11:00 a 13:00.",
            ],
            [w(d1, "12:00", "14:00"), w(d2, "12:00", "14:00"), w(d3, "10:00", "13:00")],
            [w(d2, "10:00", "12:00")],
            yes="sí",
        ),
        # High, EN: the tenant never answers.
        ("WO-005", "tenant"): Persona(["<NO RESPONSE>"]),
        ("WO-005", "handyman"): Persona(),
        # Low, ES: first asks for a slot already confirmed for WO-001, then uses the table.
        ("WO-006", "tenant"): Persona(
            [
                f"Estoy disponible el {d1} de 10:00 a 12:00.",
                f"Estoy disponible el {d2} de 09:00 a 11:00.",
            ],
            yes="sí",
        ),
        ("WO-006", "handyman"): Persona(windows=[w(d2, "09:00", "11:00")], yes="sí"),
        # Medium, EN: handyman receives two options and picks the first.
        ("WO-008", "tenant"): Persona([f"I'm free on {d3} from 14:00 to 18:00."], yes="yes"),
        ("WO-008", "handyman"): Persona(windows=[w(d3, "14:00", "16:00")], yes="sí"),
    }


def slots_in(text: str) -> list[tuple[str, str, str]]:
    dates, times = DATE.findall(text), TIME.findall(text)
    pairs = list(zip(times[0::2], times[1::2]))
    if not dates or not pairs:
        return []
    if len(dates) == 1:
        dates = dates * len(pairs)
    return [(d, s, e) for d, (s, e) in zip(dates, pairs)]


def fits(slot: tuple[str, str, str], windows: list[tuple[str, str, str]]) -> bool:
    d, s, e = slot
    return any(d == wd and ws <= s and e <= we for wd, ws, we in windows)


class Trace:
    """Reads the JSONL events the container writes to the mounted traces folder."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def events(self) -> list[dict]:
        runs = (
            sorted((self.root / "runs").glob("*/events.jsonl"))
            if (self.root / "runs").exists()
            else []
        )
        if not runs:
            return []
        out = []
        for line in runs[-1].read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return out


class Driver:
    def __init__(self, out: Path, image: str, timeout: int, gate_timeout: int) -> None:
        self.out, self.image, self.timeout, self.gate_timeout = out, image, timeout, gate_timeout
        self.today = date.today()
        self.personas = build_personas(self.today)
        self.trace = Trace(out / "traces")
        self.done: set[str] = set()
        self.todo: list[dict] = []
        self.sent: list[dict] = []
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.t0 = time.time()

    # ---------------------------------------------------------------- gates
    def gate_ok(self, gate: str | None, waited: float) -> bool:
        if gate is None or waited > self.gate_timeout:
            return True
        events = self.trace.events()
        if gate == "low_holds_ready":  # WO-003 and WO-004 tenants accepted: tentative holds exist
            who = {
                e["work_order_id"]
                for e in events
                if e["event_type"] == "participant_decision_recorded"
                and e["detail"]["actor"] == "tenant"
            }
            return {"WO-003", "WO-004"} <= who
        if gate == "preempted":  # both low-urgency holds were displaced
            gone = {
                w
                for e in events
                if e["event_type"] == "hold_transferred"
                for w in e["detail"].get("displaced_work_orders", [])
            }
            return {"WO-003", "WO-004"} <= gone
        if gate == "wo001_scheduled":
            return any(
                e["event_type"] == "terminal_result" and e["work_order_id"] == "WO-001"
                for e in events
            )
        return True

    def tenant_decisions(self, wo: str) -> int:
        return sum(
            1
            for e in self.trace.events()
            if e["event_type"] == "participant_decision_recorded"
            and e["work_order_id"] == wo
            and e["detail"]["actor"] == "tenant"
        )

    # ------------------------------------------------------------- decision
    def decide(self, wo: str, role: str, body: str) -> tuple[str, str | None] | None:
        p = self.personas[(wo, role)]
        text = body.lower()
        if sum(1 for ln in body.splitlines() if ln.strip().startswith("|")) >= 3:
            return self.statement(wo, role, p)
        if DISPLACED.search(text):
            return self.statement(wo, role, p)
        if SCHEDULED.search(text) and not ASKS_DECISION.search(text):
            return None
        if NOWAIT.search(text):
            return None
        if CHANGE.search(text):
            return p.yes, self.gate_for(wo, role)
        slots = slots_in(body)
        if len(slots) >= 2 and CONFIRM_LIST.search(text) and not OPTIONS.search(text):
            return p.yes, self.gate_for(wo, role)
        if slots:
            return self.answer_slots(wo, role, p, slots), self.gate_for(wo, role)
        return self.statement(wo, role, p)

    def statement(self, wo: str, role: str, p: Persona) -> tuple[str, str | None] | None:
        if not p.stages:
            return None
        gate = None
        if role == "tenant" and wo in ("WO-001", "WO-007") and p.idx == 0:
            gate = "low_holds_ready"
        if role == "tenant" and wo == "WO-006" and p.idx == 0:
            gate = "wo001_scheduled"
        if (
            role == "handyman"
            and wo in ("WO-003", "WO-004")
            and self.tenant_decisions(wo)
            and not self.gate_ok("preempted", 0)
        ):
            gate = "preempted"
        return p.next_stage(), gate

    def gate_for(self, wo: str, role: str) -> str | None:
        if (
            role == "handyman"
            and wo in ("WO-003", "WO-004")
            and self.tenant_decisions(wo)
            and not self.gate_ok("preempted", 0)
        ):
            return "preempted"
        return None

    def answer_slots(
        self, wo: str, role: str, p: Persona, slots: list[tuple[str, str, str]]
    ) -> str:
        if role == "tenant":
            if len(slots) == 1:
                return p.yes
            return f"{p.yes}, me viene bien el {slots[0][0]} de {slots[0][1]} a {slots[0][2]}"
        usable = [s for s in slots if fits(s, p.windows) and s not in p.rejects]
        if len(slots) == 1:
            if slots[0] in p.rejects:
                p.rejects.remove(slots[0])  # decline once, then behave
                return "no"
            return p.yes if usable else "no"
        if not usable:
            return "no"
        d, s, e = usable[0]
        return f"Sí, me viene bien el {d} de {s} a {e}"

    # ------------------------------------------------------------------ IO
    def start(self) -> subprocess.Popen:
        (self.out / "traces").mkdir(parents=True, exist_ok=True)
        os.chmod(self.out / "traces", 0o777)
        csv = (self.out / "work_orders.csv").resolve()
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            "validation-agent",
            "--env-file",
            str(REPO / ".env"),
            "-i",
            # Shorten the <NO RESPONSE> retries (defaults: 300 s x 3) to fit the run budget.
            "-e",
            "NO_RESPONSE_RETRY_WAIT_SECONDS=20",
            "-e",
            "NO_RESPONSE_MAX_RETRIES=1",
            "-e",
            "NO_RESPONSE_POLL_SECONDS=5",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            f"{csv}:/app/work_orders.csv:ro",
            "-v",
            f"{(self.out / 'traces').resolve()}:/app/traces",
            self.image,
        ]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=(self.out / "stderr.txt").open("w"),
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self.read, args=(proc,), daemon=True).start()
        return proc

    def read(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout:  # type: ignore[union-attr]
            self.lines.put(line.rstrip("\n"))
        self.lines.put(None)

    def send(self, proc: subprocess.Popen, wo: str, role: str, text: str) -> None:
        line = f"{wo}|{role} {text}"
        proc.stdin.write(line + "\n")  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]
        self.sent.append({"t": round(time.time() - self.t0, 1), "line": line})
        print(f"[{time.time() - self.t0:6.1f}s] >> {line}", flush=True)

    def run(self) -> int:
        proc = self.start()
        stdout_log = (self.out / "output.txt").open("w", encoding="utf-8")
        frame: dict | None = None
        last_line = time.time()

        def flush() -> None:
            nonlocal frame
            if frame and frame["kind"] == "ROLE":
                body = "\n".join(frame["body"]).strip()
                print(
                    f"[{time.time() - self.t0:6.1f}s] << {frame['wo']} -> {frame['label']}: {body[:90]!r}",
                    flush=True,
                )
                action = self.decide(frame["wo"], frame["label"], body)
                if action:
                    self.todo.append(
                        {
                            "wo": frame["wo"],
                            "role": frame["label"],
                            "text": action[0],
                            "gate": action[1],
                            "since": time.time(),
                        }
                    )
            frame = None

        while time.time() - self.t0 < self.timeout and len(self.done) < len(ALL_WOS):
            try:
                line = self.lines.get(timeout=0.4)
            except queue.Empty:
                line = ""
                if frame and time.time() - last_line > 2.5:
                    flush()
            else:
                if line is None:
                    break
                last_line = time.time()
                stdout_log.write(line + "\n")
                stdout_log.flush()
                m = HEADER.match(line)
                if m:
                    flush()
                    frame = {"wo": m[1], "kind": m[2], "label": m[3], "body": []}
                    if m[2] == "RESULT":
                        self.done.add(m[1])
                        print(
                            f"[{time.time() - self.t0:6.1f}s] == {m[1]} RESULT {m[3]}", flush=True
                        )
                elif frame:
                    frame["body"].append(line)
            for item in list(self.todo):
                if self.gate_ok(item["gate"], time.time() - item["since"]):
                    self.todo.remove(item)
                    self.send(proc, item["wo"], item["role"], item["text"])
                    time.sleep(0.3)
        flush()
        converged = len(self.done) == len(ALL_WOS)
        try:
            proc.stdin.close()  # type: ignore[union-attr]
            proc.wait(timeout=30)
        except Exception:
            subprocess.run(["docker", "stop", "validation-agent"], capture_output=True)
        while True:  # drain what the container printed after the last result header
            try:
                line = self.lines.get(timeout=2)
            except queue.Empty:
                break
            if line is None:
                break
            stdout_log.write(line + "\n")
        stdout_log.close()
        (self.out / "inputs.jsonl").write_text("\n".join(json.dumps(s) for s in self.sent) + "\n")
        (self.out / "driver.json").write_text(
            json.dumps(
                {
                    "converged": converged,
                    "elapsed_s": round(time.time() - self.t0, 1),
                    "today": str(self.today),
                    "sent_lines": len(self.sent),
                    "done": sorted(self.done),
                },
                indent=2,
            )
        )
        print(
            f"driver finished: converged={converged} elapsed={time.time() - self.t0:.0f}s",
            flush=True,
        )
        return 0 if converged else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", type=Path, default=HERE / "results" / time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--image", default="agent")
    ap.add_argument("--no-build", action="store_true", help="reuse an existing image")
    ap.add_argument("--timeout", type=int, default=1800, help="whole-run limit in seconds")
    ap.add_argument(
        "--gate-timeout", type=int, default=240, help="release a held reply after this many seconds"
    )
    args = ap.parse_args()
    if not (REPO / ".env").exists():
        sys.exit(".env with ANTHROPIC_API_KEY is required at the repository root")
    if not args.no_build:
        subprocess.run(["docker", "build", "-t", args.image, str(REPO)], check=True)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "work_orders.csv").write_text(
        (HERE / "work_orders.csv").read_text(encoding="utf-8"), encoding="utf-8"
    )
    status = Driver(args.out, args.image, args.timeout, args.gate_timeout).run()
    subprocess.run([sys.executable, str(HERE / "metrics.py"), str(args.out)], check=False)
    return status


if __name__ == "__main__":
    sys.exit(main())
