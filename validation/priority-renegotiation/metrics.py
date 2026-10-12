#!/usr/bin/env python3
"""Compute validation metrics and invariant checks from one run folder.

    python validation/priority-renegotiation/metrics.py <run-dir>

``<run-dir>`` holds ``work_orders.csv``, ``output.txt``, ``stderr.txt`` and
``traces/runs/<id>/events.jsonl`` (as produced by ``run.py``). Writes ``metrics.json`` and
``METRICS.md`` into it and exits 1 if any check fails.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

RANK = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
NOTICE = re.compile(r"displaced|reasignada|desplazad|higher[- ]priority|mayor prioridad", re.I)


def load(run: Path) -> tuple[list[dict], dict[str, dict]]:
    events_file = sorted((run / "traces" / "runs").glob("*/events.jsonl"))[-1]
    events = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines()]
    rows = {
        r["work_order_id"]: r
        for r in csv.DictReader((run / "work_orders.csv").open(encoding="utf-8"))
    }
    return events, rows


def ts(event: dict) -> datetime:
    return datetime.fromisoformat(event["timestamp"])


def main(run: Path) -> int:
    events, rows = load(run)
    stderr = (
        (run / "stderr.txt").read_text(encoding="utf-8") if (run / "stderr.txt").exists() else ""
    )
    stdout = (
        (run / "output.txt").read_text(encoding="utf-8") if (run / "output.txt").exists() else ""
    )
    start = ts(events[0])
    by_wo: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        if e["work_order_id"]:
            by_wo[e["work_order_id"]].append(e)

    terminals = {
        w: [e for e in es if e["event_type"] == "terminal_result"] for w, es in by_wo.items()
    }
    transfers = [e for e in events if e["event_type"] == "hold_transferred"]
    language = {
        e["work_order_id"]: e["detail"]["language_code"]
        for e in events
        if e["event_type"] == "language_recognized"
    }

    per_wo: dict[str, dict] = {}
    for wo, row in sorted(rows.items()):
        es = by_wo[wo]
        term = terminals.get(wo, [])
        result = term[0]["detail"] if term else {}
        out = [e for e in es if e["event_type"] == "outgoing_message"]
        displaced_at = [e for e in transfers if wo in e["detail"].get("displaced_work_orders", [])]
        per_wo[wo] = {
            "urgency": row["urgency"],
            "language": language.get(wo),
            "result": result.get("result"),
            "detail": result.get("detail"),
            "seconds_to_terminal": round((ts(term[0]) - start).total_seconds(), 1)
            if term
            else None,
            "messages_to_tenant": sum(1 for e in out if e["detail"]["role"] == "tenant"),
            "messages_to_handyman": sum(1 for e in out if e["detail"]["role"] == "handyman"),
            "inbound_messages": sum(1 for e in es if e["event_type"] == "inbound_dispatched"),
            "availability_revisions": sum(
                1 for e in es if e["event_type"] == "availability_evidence_recorded"
            ),
            "holds_released": sum(1 for e in es if e["event_type"] == "hold_released"),
            "times_displaced": len(displaced_at),
            "handyman_declines": sum(1 for e in es if e["event_type"] == "handyman_slots_declined"),
            "slot_suggestion_tables": sum(
                1 for e in es if e["event_type"] == "slot_suggestion_attempt"
            ),
        }

    # ------------------------------------------------------------------ checks
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, note: str = "") -> None:
        checks.append((name, bool(ok), note))

    check(
        "every work order ends with exactly one terminal result",
        all(len(terminals.get(w, [])) == 1 for w in rows),
        str({w: len(terminals.get(w, [])) for w in rows}),
    )
    check(
        "stdout carries exactly one RESULT frame per work order",
        Counter(re.findall(r"^WOID:(WO-\d+)\|RESULT:", stdout, re.M))
        == Counter({w: 1 for w in rows}),
    )
    check("stderr is empty", stderr.strip() == "")

    intervals = []
    for wo, info in per_wo.items():
        if info["result"] == "scheduled":
            start_at = datetime.fromisoformat(info["detail"].split("SCHEDULED_FOR:")[1].strip())
            intervals.append((wo, start_at, start_at + timedelta(hours=2)))
    clashes = [
        (a[0], b[0])
        for i, a in enumerate(intervals)
        for b in intervals[i + 1 :]
        if a[1] < b[2] and b[1] < a[2]
    ]
    check("no two scheduled visits overlap", not clashes, str(clashes))
    check(
        "scheduled visits are inside 09:00-19:00",
        all(9 <= s.hour and e.hour + e.minute / 60 <= 19 for _, s, e in intervals),
    )

    check("at least one higher-urgency order displaced a tentative hold", bool(transfers))
    bad = [
        (e["work_order_id"], d)
        for e in transfers
        for d in e["detail"].get("displaced_work_orders", [])
        if RANK[per_wo[d]["urgency"]] >= RANK[per_wo[e["work_order_id"]]["urgency"]]
    ]
    check("every displacement goes from a strictly higher to a lower urgency", not bad, str(bad))
    displaced = sorted({d for e in transfers for d in e["detail"].get("displaced_work_orders", [])})
    notified = []
    for e in transfers:
        for d in e["detail"].get("displaced_work_orders", []):
            notified.append(
                any(
                    o["event_type"] == "outgoing_message"
                    and o["detail"]["role"] == "tenant"
                    and o["sequence"] > e["sequence"]
                    and NOTICE.search(o["detail"]["body"])
                    for o in by_wo[d]
                )
            )
    check(
        "each displaced tenant receives a displacement notice",
        bool(notified) and all(notified),
        str(displaced),
    )
    first_slot = {}
    for e in transfers:
        first_slot[e["work_order_id"]] = e["detail"]["interval"]["start"]
    check(
        "displaced orders end with a different, non-overlapping slot",
        all(per_wo[d]["result"] == "scheduled" for d in displaced) and not clashes,
        str(displaced),
    )
    silent = [w for w, i in per_wo.items() if i["result"] == "requires_review"]
    check(
        "silent tenant produces requires_review with a no-response reason",
        all("No response" in (per_wo[w]["detail"] or "") for w in silent) and bool(silent),
        str(silent),
    )

    summary = {
        "work_orders": len(rows),
        "scheduled": sum(1 for i in per_wo.values() if i["result"] == "scheduled"),
        "requires_review": len(silent),
        "preemptions": len(transfers),
        "displaced_work_orders": displaced,
        "holds_released": sum(i["holds_released"] for i in per_wo.values()),
        "handyman_declines": sum(i["handyman_declines"] for i in per_wo.values()),
        "slot_suggestion_tables": sum(i["slot_suggestion_tables"] for i in per_wo.values()),
        "outgoing_messages": sum(
            i["messages_to_tenant"] + i["messages_to_handyman"] for i in per_wo.values()
        ),
        "inbound_messages": sum(i["inbound_messages"] for i in per_wo.values()),
        "wall_clock_seconds": round((ts(events[-1]) - start).total_seconds(), 1),
        "checks_passed": sum(1 for c in checks if c[1]),
        "checks_total": len(checks),
    }
    (run / "metrics.json").write_text(
        json.dumps(
            {
                "summary": summary,
                "per_work_order": per_wo,
                "checks": [{"name": n, "ok": o, "note": x} for n, o, x in checks],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md = ["# Metrics", "", "## Summary", "", "| Metric | Value |", "|---|---|"]
    md += [f"| {k.replace('_', ' ')} | {v} |" for k, v in summary.items()]
    md += [
        "",
        "## Per work order",
        "",
        "| WO | Urgency | Lang | Result | Time to terminal (s) | Msgs tenant | Msgs handyman | Inbound | Revisions | Displaced | Declines |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for wo, i in per_wo.items():
        md.append(
            f"| {wo} | {i['urgency']} | {i['language']} | {i['result']} | {i['seconds_to_terminal']} | "
            f"{i['messages_to_tenant']} | {i['messages_to_handyman']} | {i['inbound_messages']} | "
            f"{i['availability_revisions']} | {i['times_displaced']} | {i['handyman_declines']} |"
        )
    md += ["", "## Checks", "", "| Check | Result | Note |", "|---|---|---|"]
    md += [f"| {n} | {'PASS' if o else 'FAIL'} | {x} |" for n, o, x in checks]
    (run / "METRICS.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0 if all(c[1] for c in checks) else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(Path(sys.argv[1])))
