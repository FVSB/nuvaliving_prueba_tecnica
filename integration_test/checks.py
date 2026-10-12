"""Reusable checks over what one step produced (see runner.StepView)."""

from __future__ import annotations

import re

from runner import Check, StepView


def _detail_matches(event: dict, expected: dict) -> bool:
    detail = event.get("detail", {})
    return all(detail.get(key) == value for key, value in expected.items())


def event(event_type: str, known_issue: str | None = None, **detail) -> Check:
    return Check(
        f"event {event_type} {detail or ''}".strip(),
        lambda v: any(_detail_matches(e, detail) for e in v.events_of(event_type)),
        known_issue,
    )


def no_event(event_type: str, known_issue: str | None = None) -> Check:
    return Check(f"no {event_type} event", lambda v: not v.events_of(event_type), known_issue)


def rejected(code: str, known_issue: str | None = None) -> Check:
    return event("availability_rejected", known_issue, code=code)


def no_evidence(known_issue: str | None = None) -> Check:
    return no_event("availability_evidence_recorded", known_issue)


def evidence(actor: str | None = None, known_issue: str | None = None) -> Check:
    detail = {"actor": actor} if actor else {}
    return event("availability_evidence_recorded", known_issue, **detail)


def no_evidence_by(actor: str, known_issue: str | None = None) -> Check:
    return Check(
        f"no availability evidence recorded as {actor}",
        lambda v: (
            not any(
                e["detail"].get("actor") == actor
                for e in v.events_of("availability_evidence_recorded")
            )
        ),
        known_issue,
    )


def guard(action: str, known_issue: str | None = None) -> Check:
    return event("injection_guard_screened", known_issue, action=action)


def message_rejected(reason: str, known_issue: str | None = None) -> Check:
    return Check(
        f"message_rejected reason={reason}",
        lambda v: any(
            e["detail"].get("reason") == reason
            for e in v.events_of("message_rejected")
            + [r for r in v.runtime if r["event_type"] == "message_rejected"]
        ),
        known_issue,
    )


def malformed_input(known_issue: str | None = None) -> Check:
    return Check(
        "malformed_input traced in runtime.jsonl",
        lambda v: any(r["event_type"] == "malformed_input" for r in v.runtime),
        known_issue,
    )


def no_dispatch(known_issue: str | None = None) -> Check:
    return no_event("inbound_dispatched", known_issue)


def silent(known_issue: str | None = None) -> Check:
    return Check("nothing is written back to the sender", lambda v: not v.messages, known_issue)


def replied(known_issue: str | None = None) -> Check:
    return Check("the sender gets a reply", lambda v: bool(v.messages), known_issue)


def reply_has(*needles: str, known_issue: str | None = None) -> Check:
    lowered = [needle.lower() for needle in needles]
    return Check(
        f"reply mentions any of {list(needles)}",
        lambda v: any(n in m.body.lower() for m in v.messages for n in lowered),
        known_issue,
    )


def reply_lacks(*needles: str, known_issue: str | None = None) -> Check:
    lowered = [needle.lower() for needle in needles]
    return Check(
        f"no reply mentions {list(needles)}",
        lambda v: not any(n in m.body.lower() for m in v.messages for n in lowered),
        known_issue,
    )


def reply_lacks_regex(pattern: str, known_issue: str | None = None) -> Check:
    compiled = re.compile(pattern, re.IGNORECASE)
    return Check(
        f"no reply matches /{pattern}/",
        lambda v: not any(compiled.search(m.body) for m in v.messages),
        known_issue,
    )


def reply_to(role: str, work_order: str | None = None, known_issue: str | None = None) -> Check:
    return Check(
        f"a reply addressed to the {role}" + (f" of {work_order}" if work_order else ""),
        lambda v: any(
            m.label == role and (work_order is None or m.work_order_id == work_order)
            for m in v.messages
        ),
        known_issue,
    )


def no_decision(known_issue: str | None = None) -> Check:
    return no_event("participant_decision_recorded", known_issue)


def decision(actor: str, answer: str = "yes", known_issue: str | None = None) -> Check:
    return event("participant_decision_recorded", known_issue, actor=actor, decision=answer)


def scheduled(known_issue: str | None = None) -> Check:
    return Check(
        "a RESULT:scheduled frame is written",
        lambda v: any(t.label == "scheduled" for t in v.terminals),
        known_issue,
    )


def not_scheduled(known_issue: str | None = None) -> Check:
    return Check(
        "no RESULT:scheduled frame",
        lambda v: not any(t.label == "scheduled" for t in v.terminals),
        known_issue,
    )


def terminal(result: str, known_issue: str | None = None) -> Check:
    return Check(
        f"terminal frame RESULT:{result}",
        lambda v: any(t.label == result for t in v.terminals),
        known_issue,
    )


def terminal_reason_has(*needles: str, known_issue: str | None = None) -> Check:
    lowered = [needle.lower() for needle in needles]
    return Check(
        f"terminal REASON mentions any of {list(needles)}",
        lambda v: any(n in t.body.lower() for t in v.terminals for n in lowered),
        known_issue,
    )


def slot_table(known_issue: str | None = None) -> Check:
    return Check(
        "a slot table (SLOT- rows) is shown",
        lambda v: any("SLOT-" in m.body for m in v.messages),
        known_issue,
    )


def no_slot_table(known_issue: str | None = None) -> Check:
    return Check(
        "no slot table is shown",
        lambda v: not any("SLOT-" in m.body for m in v.messages),
        known_issue,
    )


def slots_not_after(last_date: str, known_issue: str | None = None) -> Check:
    """Slot ids look like SLOT-20261018T1500Z01 (UTC); compare the date part."""
    limit = last_date.replace("-", "")

    def test(view: StepView) -> bool:
        found = re.findall(r"SLOT-(\d{8})T", " ".join(m.body for m in view.messages))
        return all(day <= limit for day in found)

    return Check(f"no slot after {last_date}", test, known_issue)


def slot_on(date: str, known_issue: str | None = None) -> Check:
    day = date.replace("-", "")
    return Check(
        f"the slot table lists at least one slot on {date}",
        lambda v: any(
            d == day for d in re.findall(r"SLOT-(\d{8})T", " ".join(m.body for m in v.messages))
        ),
        known_issue,
    )


def only_slots_on(date: str, known_issue: str | None = None) -> Check:
    day = date.replace("-", "")

    def test(view: StepView) -> bool:
        found = re.findall(r"SLOT-(\d{8})T", " ".join(m.body for m in view.messages))
        return bool(found) and all(d == day for d in found)

    return Check(f"only slots of {date} are listed", test, known_issue)


def no_overlapping_appointments(known_issue: str | None = None) -> Check:
    def test(view: StepView) -> bool:
        starts = [
            line.split(":", 1)[1].strip()
            for t in view.terminals
            if t.label == "scheduled"
            for line in t.body.splitlines()
            if line.startswith("SCHEDULED_FOR")
        ]
        return len(starts) == len(set(starts))

    return Check("no two appointments share the same start", test, known_issue)
