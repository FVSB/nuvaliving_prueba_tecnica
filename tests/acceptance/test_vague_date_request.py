import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from maintenance_agent.__main__ import run
from maintenance_agent.application.conversation import (
    AvailabilityInterpretation,
    MessageClass,
)
from maintenance_agent.application.language_recognition import StaticLanguageRecognizer
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.negotiation import TimeInterval
from tests.integration.fakes import BAD_PROSE, FakeConversationHandler, FakeStdinReader

_NOW = datetime.fromisoformat("2026-10-16T12:00:00+02:00")


CSV = Path(__file__).resolve().parents[1] / "fixtures" / "work_orders.csv"
VAGUE = AvailabilityInterpretation((), False, True, classification=MessageClass.VAGUE_DATE_REQUEST)


def _events(tmp_path: Path) -> list[dict]:
    (path,) = (tmp_path / "traces" / "runs").glob("*/events.jsonl")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def _run(tmp_path, monkeypatch, handler, lines):
    monkeypatch.setenv("TRACES_DIR", str(tmp_path / "traces"))
    await run(
        now=_NOW,
        csv_path=CSV,
        stdin_reader=FakeStdinReader(lines),
        conversation_handler=handler,
        language_recognizer=StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.SPANISH)
        ),
    )


@pytest.mark.asyncio
async def test_vague_request_gets_table_not_generic_prompt(capsys, tmp_path, monkeypatch):
    handler = FakeConversationHandler(availability_results={"tenant": [VAGUE]})
    await _run(
        tmp_path,
        monkeypatch,
        handler,
        ["WO-002|tenant esta semana por la tarde que dias pueden ser?"],
    )
    assert len(handler.slot_compose_calls) == 1
    assert not any(c[0] == "clarify_absolute_availability" for c in handler.compositions)
    events = _events(tmp_path)
    attempts = [e for e in events if e["event_type"] == "slot_suggestion_attempt"]
    assert len(attempts) == 1 and attempts[0]["work_order_id"] == "WO-002"
    assert attempts[0]["detail"]["attempt"] == 1 and attempts[0]["detail"]["valid"] is True
    assert attempts[0]["detail"]["table_rows"] > 0
    assert "RESULT:" not in capsys.readouterr().out  # order stays non-terminal


@pytest.mark.asyncio
async def test_three_failures_emit_fallback_then_next_message_resumes(
    capsys, tmp_path, monkeypatch
):
    start = datetime(2026, 10, 20, 7, tzinfo=timezone.utc)
    explicit = AvailabilityInterpretation(
        (TimeInterval(start, start.replace(hour=9)),),
        True,
        False,
        classification=MessageClass.EXPLICIT_INTERVALS,
    )
    handler = FakeConversationHandler(
        availability_results={"tenant": [VAGUE, explicit]},
        slot_prose=[BAD_PROSE] * 3,
    )
    await _run(
        tmp_path,
        monkeypatch,
        handler,
        ["WO-002|tenant cuando puedan", "WO-002|tenant el 20 de octubre de 9 a 11"],
    )
    events = [e for e in _events(tmp_path) if e["work_order_id"] == "WO-002"]
    kinds = [e["event_type"] for e in events]
    assert kinds.count("slot_suggestion_attempt") == 3
    assert kinds.count("slot_suggestion_feedback") == 3
    assert kinds.count("slot_fallback_emitted") == 1
    fallback = next(e for e in events if e["event_type"] == "slot_fallback_emitted")
    assert fallback["detail"]["ambiguity_reason"] == "other"
    assert "next_slot_id" not in fallback["detail"]
    assert kinds.index("slot_fallback_emitted") < kinds.index("availability_evidence_recorded")
    assert "RESULT:requires_review" not in capsys.readouterr().out
