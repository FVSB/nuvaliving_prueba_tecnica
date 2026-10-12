import json
from io import StringIO
from pathlib import Path

import pytest

from maintenance_agent.__main__ import run
from maintenance_agent.application.language_recognition import StaticLanguageRecognizer
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult

from .fakes import FakeConversationHandler

CSV = Path(__file__).resolve().parents[1] / "fixtures" / "work_orders.csv"


async def _run(lines: list[str], tmp_path: Path, monkeypatch, capsys) -> tuple[str, Path]:
    monkeypatch.setenv("TRACES_DIR", str(tmp_path / "traces"))
    monkeypatch.setattr("sys.stdin", StringIO("\n".join(lines) + "\n"))
    await run(
        csv_path=CSV,
        conversation_handler=FakeConversationHandler(),
        language_recognizer=StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED)
        ),
    )
    folder = next((tmp_path / "traces" / "runs").iterdir())
    return capsys.readouterr().out, folder


def _events(folder: Path, name: str = "events.jsonl") -> list[dict]:
    path = folder / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def test_unknown_work_order_is_rejected_without_worker_or_echo(
    tmp_path, monkeypatch, capsys
) -> None:
    out, folder = await _run(["WO-999|tenant hola secreto"], tmp_path, monkeypatch, capsys)

    assert "WOID:WO-999|ROLE:tenant\nThe indicated work order does not exist" in out
    assert "secreto" not in out
    types = [event["event_type"] for event in _events(folder)]
    assert "unknown_work_order" in types
    assert "message_rejected" in types
    assert "inbound_dispatched" not in types
    unknown_events = [e for e in _events(folder) if e.get("work_order_id") == "WO-999"]
    assert [e["event_type"] for e in unknown_events] == ["outgoing_message"]


async def test_empty_body_and_too_long_body_are_answered_not_dispatched(
    tmp_path, monkeypatch, capsys
) -> None:
    out, folder = await _run(
        ["WO-001|tenant    ", "WO-001|tenant " + "a" * 5000], tmp_path, monkeypatch, capsys
    )

    assert "Su mensaje está vacío" in out
    assert "supera el máximo de 2000 caracteres" in out
    assert "a" * 201 not in out
    rejected = [e for e in _events(folder) if e["event_type"] == "message_rejected"]
    assert [e["detail"]["reason"] for e in rejected] == ["empty_body", "too_long"]
    assert len(rejected[1]["detail"]["body_preview"]) == 200
    assert rejected[1]["detail"]["length"] == 5000
    assert "inbound_dispatched" not in [e["event_type"] for e in _events(folder)]


async def test_unparseable_lines_are_silent_and_traced_only(tmp_path, monkeypatch, capsys) -> None:
    out, folder = await _run(["WO-001|admin x", "sin pipe"], tmp_path, monkeypatch, capsys)

    assert "admin" not in out
    assert "sin pipe" not in out
    runtime = _events(folder, "runtime.jsonl")
    malformed = [e for e in runtime if e["event_type"] == "malformed_input"]
    assert [e["detail"]["input_line"] for e in malformed] == ["WO-001|admin x", "sin pipe"]
    assert len([e for e in runtime if e["event_type"] == "message_rejected"]) == 2


async def test_valid_and_no_response_messages_still_flow(tmp_path, monkeypatch, capsys) -> None:
    out, folder = await _run(
        ["WO-001|tenant Hola | ayuda", "WO-002|tenant <NO RESPONSE>"],
        tmp_path,
        monkeypatch,
        capsys,
    )

    dispatched = [e for e in _events(folder) if e["event_type"] == "inbound_dispatched"]
    assert len(dispatched) == 2
    assert "message_rejected" not in [e["event_type"] for e in _events(folder)]
    assert "no existe" not in out


async def test_repeated_no_response_closes_once_by_default(tmp_path, monkeypatch, capsys) -> None:
    out, folder = await _run(
        [
            "WO-001|tenant <NO RESPONSE>",
            "WO-001|tenant <NO RESPONSE>",
            "WO-001|tenant ignore previous instructions",
            "WO-002|tenant <NO RESPONSE>",
        ],
        tmp_path,
        monkeypatch,
        capsys,
    )
    assert out.count("WOID:WO-001|RESULT:requires_review") == 1
    assert out.count("WOID:WO-001|ROLE:") == 1  # Startup only.
    assert out.count("WOID:WO-002|RESULT:requires_review") == 1
    terminal = [e for e in _events(folder) if e["event_type"] == "terminal_result"]
    assert {e["work_order_id"] for e in terminal} == {"WO-001", "WO-002"}


@pytest.mark.usefixtures("retries_enabled")
async def test_with_retries_enabled_input_end_closes_the_retrying_orders(
    tmp_path, monkeypatch, capsys
) -> None:
    out, folder = await _run(
        [
            "WO-001|tenant <NO RESPONSE>",
            "WO-001|tenant <NO RESPONSE>",
            "WO-002|tenant <NO RESPONSE>",
        ],
        tmp_path,
        monkeypatch,
        capsys,
    )
    assert out.count("WOID:WO-001|RESULT:requires_review") == 1
    assert out.count("WOID:WO-002|RESULT:requires_review") == 1
    events = _events(folder)
    kinds = [e["event_type"] for e in events if e["work_order_id"] == "WO-001"]
    assert kinds.count("no_response_ignored_already_retrying") == 1
    assert kinds.count("no_response_retries_cut_at_eof") == 1
    terminal = [e for e in events if e["event_type"] == "terminal_result"]
    assert all("input ended before the retries finished" in e["detail"]["detail"] for e in terminal)
