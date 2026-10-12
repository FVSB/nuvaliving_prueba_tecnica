"""Turn a live run into markdown transcripts and a bottleneck summary.

Usage: uv run python tests/live/report.py [runs/<timestamp>]   (default: newest run)

Writes `<run>/report/<scenario>.md` (the conversation as the participants saw it, with the
system's decisions interleaved) and `<run>/report/SUMMARY.md` (signals per scenario).
"""

import json
import sys
from collections import Counter
from pathlib import Path

RUNS = Path(__file__).parent / "runs"

# Event types that point at friction in the conversation, with a short reading of each.
SIGNALS = {
    "slot_suggestion_feedback": "validator rejected a slot-suggestion draft",
    "slot_fallback_emitted": "fell back to the fixed table text",
    "availability_rejected": "date/time refused as invalid",
    "handyman_slots_declined": "handyman declined the offered slots",
    "message_rejected": "inbound line rejected (format)",
    "availability_dispute_started": "tenant availability contradicted an earlier one",
    "proposal_withdrawn": "proposal withdrawn",
    "hold_released": "slot hold released",
    "slot_reply_translated": "slot prose had to be translated to the tenant's language",
    "slot_reply_language_mismatch": "slot prose stayed in the wrong language after 3 cycles",
}


def _events(scenario: Path) -> list[dict]:
    files = sorted((scenario / "traces" / "runs").glob("*/events.jsonl"))
    if not files:
        return []
    rows = []
    for line in files[0].read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.strip().splitlines())


def _transcript(name: str, events: list[dict]) -> tuple[str, Counter]:
    signals: Counter = Counter()
    lines = [f"# {name}", ""]
    for event in events:
        kind, detail = event["event_type"], event.get("detail", {})
        wo = event.get("work_order_id") or "-"
        if kind == "inbound_dispatched":
            lines += [f"### {wo} · {detail.get('role')} says", _quote(detail.get("body", "")), ""]
        elif kind == "outgoing_message":
            heading = f"### {wo} · system → {detail.get('role')}"
            lines += [heading, _quote(detail.get("body", "")), ""]
        elif kind == "injection_guard_screened" and detail.get("action") != "pass":
            lines += [f"- guard: `{detail.get('action')}` ({detail.get('reason')})", ""]
        elif kind == "slot_suggestion_attempt":
            attempt, valid = detail.get("attempt"), detail.get("valid")
            lines += [f"- slot draft attempt {attempt}: valid={valid}", ""]
        elif kind in SIGNALS or kind.startswith("slot_reply_"):
            note = detail.get("feedback") or detail.get("reason") or detail.get("ambiguity_reason")
            lines += [f"- **{kind}**" + (f": {note}" if note else ""), ""]
        if kind == "slot_suggestion_attempt" and not detail.get("valid"):
            signals["slot_draft_invalid"] += 1
        elif kind in SIGNALS:
            signals[kind] += 1
    return "\n".join(lines), signals


def main() -> int:
    run = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(RUNS.iterdir())[-1]
    out = run / "report"
    out.mkdir(exist_ok=True)
    totals: Counter = Counter()
    rows = []
    for scenario in sorted(p for p in run.iterdir() if p.is_dir() and p.name != "report"):
        text, signals = _transcript(scenario.name, _events(scenario))
        (out / f"{scenario.name}.md").write_text(text + "\n", encoding="utf-8")
        totals += signals
        rows.append((scenario.name, signals))
    rows.sort(key=lambda row: -sum(row[1].values()))
    summary = [f"# Bottleneck summary · {run.name}", "", "## Totals", ""]
    summary += [f"- {key}: {count}" for key, count in totals.most_common()] or ["- none"]
    summary += ["", "## Scenarios by friction", "", "| Scenario | Signals |", "|---|---|"]
    for name, signals in rows:
        detail = ", ".join(f"{k}×{v}" for k, v in signals.most_common()) or "-"
        summary.append(f"| [{name}]({name}.md) | {detail} |")
    (out / "SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} transcripts and SUMMARY.md to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
