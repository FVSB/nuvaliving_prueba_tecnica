"""NO RESPONSE starts timed retries (reminders), cancelled by the silent role's answer."""

import asyncio
import json
from pathlib import Path

import pytest

from maintenance_agent.__main__ import run
from maintenance_agent.application.language_recognition import StaticLanguageRecognizer
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.infrastructure.cli_transport import parse_inbound_message

from .fakes import FakeConversationHandler

CSV = Path(__file__).resolve().parents[1] / "fixtures" / "work_orders.csv"


class TimedReader:
    """Yield protocol lines, pausing for numbers (seconds), then end the input."""

    def __init__(self, *items: str | float) -> None:
        self._items = items

    async def messages(self):
        for item in self._items:
            if isinstance(item, float):
                await asyncio.sleep(item)
            else:
                yield parse_inbound_message(item)


async def _run(reader: TimedReader, tmp_path, monkeypatch, capsys, retries: int = 2):
    monkeypatch.setenv("TRACES_DIR", str(tmp_path / "traces"))
    monkeypatch.setenv("NO_RESPONSE_RETRY_WAIT_SECONDS", "0.2")
    monkeypatch.setenv("NO_RESPONSE_MAX_RETRIES", str(retries))
    monkeypatch.setenv("NO_RESPONSE_POLL_SECONDS", "0.02")
    await run(
        csv_path=CSV,
        stdin_reader=reader,
        conversation_handler=FakeConversationHandler(),
        language_recognizer=StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
        ),
    )
    folder = next((tmp_path / "traces" / "runs").iterdir())
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
    return capsys.readouterr().out, events


@pytest.mark.usefixtures("retries_enabled")
async def test_silence_gets_reminders_then_closes_after_the_retries(
    tmp_path, monkeypatch, capsys
) -> None:
    out, events = await _run(
        TimedReader("WO-001|tenant <NO RESPONSE>", 1.2), tmp_path, monkeypatch, capsys
    )
    kinds = [e["event_type"] for e in events if e["work_order_id"] == "WO-001"]
    assert kinds.count("no_response_retry_scheduled") == 1
    assert kinds.count("no_response_retry_sent") == 2
    assert kinds.count("no_response_retries_cut_at_eof") == 0
    assert out.count("Reminder:") == 2
    assert out.count("WOID:WO-001|RESULT:requires_review") == 1
    assert "after 2 retries." in out


@pytest.mark.usefixtures("retries_enabled")
async def test_the_silent_role_answering_cancels_the_retries(tmp_path, monkeypatch, capsys) -> None:
    out, events = await _run(
        TimedReader("WO-001|tenant <NO RESPONSE>", 0.05, "WO-001|tenant hola", 0.8),
        tmp_path,
        monkeypatch,
        capsys,
    )
    kinds = [e["event_type"] for e in events if e["work_order_id"] == "WO-001"]
    assert "no_response_retry_cancelled" in kinds
    assert "no_response_retry_sent" not in kinds
    assert "Reminder:" not in out
    assert "WOID:WO-001|RESULT:" not in out


async def test_without_retries_the_sentinel_closes_the_order_at_once(
    tmp_path, monkeypatch, capsys
) -> None:
    """Default (0 retries): no waiting, no reminders, the original immediate closure."""
    out, events = await _run(
        TimedReader("WO-001|tenant <NO RESPONSE>", 0.1), tmp_path, monkeypatch, capsys, retries=0
    )
    kinds = [e["event_type"] for e in events if e["work_order_id"] == "WO-001"]
    assert "no_response_retry_scheduled" not in kinds
    assert "Reminder:" not in out
    assert out.count("WOID:WO-001|RESULT:requires_review") == 1
    reason = next(line for line in out.splitlines() if line.startswith("REASON:"))
    assert reason.startswith("REASON:No response from tenant while awaiting tenant_availability.")
    assert "retries" not in reason


async def test_messages_to_a_terminal_order_are_ignored_with_a_trace(
    tmp_path, monkeypatch, capsys
) -> None:
    out, events = await _run(
        TimedReader("WO-001|tenant <NO RESPONSE>", 0.3, "WO-001|tenant yes", 0.1),
        tmp_path,
        monkeypatch,
        capsys,
        retries=0,
    )
    assert out.count("WOID:WO-001|RESULT:requires_review") == 1
    ignored = [e for e in events if e["event_type"] == "message_ignored_after_terminal"]
    assert [e["detail"]["is_no_response"] for e in ignored] == [False]
