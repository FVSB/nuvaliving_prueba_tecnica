import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from maintenance_agent.__main__ import run
from maintenance_agent.application.language_recognition import StaticLanguageRecognizer
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.infrastructure.cli_transport import parse_inbound_message
from tests.integration.fakes import FakeConversationHandler, FakeStdinReader

_NOW = datetime.fromisoformat("2026-10-16T12:00:00+02:00")


@pytest.mark.asyncio
async def test_cli_runs_isolated_orders_and_emits_one_terminal_result_each(
    capsys, tmp_path: Path, monkeypatch
):
    start = datetime(2026, 10, 20, 7, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    monkeypatch.setenv("TRACES_DIR", str(tmp_path / "traces"))
    await run(
        now=_NOW,
        csv_path=Path(__file__).resolve().parents[1] / "fixtures" / "work_orders.csv",
        stdin_reader=FakeStdinReader(
            [
                "WO-001|tenant I can do October 20 from 9 to 11",
                "WO-001|handyman I am available October 20 from 9 to 11",
                "WO-001|handyman yes",
                "WO-001|tenant yes",
                "WO-001|handyman yes",
                "WO-002|handyman <NO RESPONSE>",
            ]
        ),
        conversation_handler=FakeConversationHandler(
            availability={
                "tenant": ((start.isoformat(), end.isoformat()),),
                "handyman": ((start.isoformat(), end.isoformat()),),
            },
        ),
        language_recognizer=StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
        ),
    )
    output = capsys.readouterr().out
    assert output.count("WOID:WO-001|RESULT:scheduled") == 1
    assert output.count("WOID:WO-002|RESULT:requires_review") == 1
    assert output.count("RESULT:") == 2
    assert "SCHEDULED_FOR:2026-10-20T09:00:00+02:00" in output
    trace_files = list((tmp_path / "traces" / "runs").glob("*/events.jsonl"))
    assert len(trace_files) == 1
    events = [json.loads(line) for line in trace_files[0].read_text(encoding="utf-8").splitlines()]
    completed = [e for e in events if e["event_type"] == "terminal_result"]
    assert len(completed) == 2
    scheduled = next(e for e in completed if e["detail"]["result"] == "scheduled")
    confirmations = [
        e
        for e in events
        if e["event_type"] == "outgoing_message"
        and e["work_order_id"] == "WO-001"
        and "confirm the scheduled visit" in e["detail"]["body"]
    ]
    assert {e["detail"]["role"] for e in confirmations} == {"tenant", "handyman"}
    assert all(e["sequence"] < scheduled["sequence"] for e in confirmations)
    assert any(
        item["event_type"] == "availability_evidence_recorded"
        and item["work_order_id"] == "WO-001"
        and item["detail"]["actor"] == "tenant"
        and item["detail"]["intervals"]
        for item in events
    )
    assert any(
        item["event_type"] == "participant_decision_recorded"
        and item["detail"]["actor"] == "tenant"
        and item["detail"]["decision"] == "yes"
        for item in events
    )


@pytest.mark.asyncio
async def test_priority_transfer_notifies_displaced_tenant_with_known_alternative(
    capsys, tmp_path: Path, monkeypatch
):
    csv_path = tmp_path / "work-orders.csv"
    csv_path.write_text(
        "work_order_id,work_order,address,description,reported_at,urgency\n"
        "WO-LOW,Leak,Low Street,Water leak,2026-10-12T09:00:00+02:00,Low\n"
        "WO-HIGH,Leak,High Street,Water leak,2026-10-12T09:00:00+02:00,Critical\n",
        encoding="utf-8",
    )
    start = datetime(2026, 10, 20, 7, tzinfo=timezone.utc)
    end = start + timedelta(hours=4)

    class OrderedReader:
        async def messages(self):
            lines = [
                "WO-LOW|tenant available",
                "WO-LOW|handyman available",
                "WO-LOW|handyman yes",
                "WO-LOW|tenant yes",
                "WO-HIGH|tenant available",
                "WO-HIGH|handyman available",
                "WO-HIGH|handyman yes",
                "WO-HIGH|tenant yes",
            ]
            for line in lines:
                yield parse_inbound_message(line)
                if line == "WO-HIGH|tenant yes":
                    await asyncio.sleep(0.02)
            for line in (
                "WO-LOW|tenant yes",
                "WO-LOW|tenant yes",
                "WO-LOW|handyman yes",
                "WO-HIGH|handyman yes",
            ):
                yield parse_inbound_message(line)

    monkeypatch.setenv("TRACES_DIR", str(tmp_path / "traces"))
    await run(
        now=_NOW,
        csv_path=csv_path,
        stdin_reader=OrderedReader(),
        conversation_handler=FakeConversationHandler(
            availability={
                "tenant": ((start.isoformat(), end.isoformat()),),
                "handyman": ((start.isoformat(), end.isoformat()),),
            }
        ),
        language_recognizer=StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
        ),
    )

    output = capsys.readouterr().out
    assert output.count("WOID:WO-LOW|RESULT:scheduled") == 1
    assert output.count("WOID:WO-HIGH|RESULT:scheduled") == 1
    assert "notify the tenant that their tentative visit was displaced" in output
    assert "2026-10-20T11:00:00+02:00" in output
