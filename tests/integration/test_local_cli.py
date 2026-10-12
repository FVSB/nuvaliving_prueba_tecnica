from pathlib import Path

from maintenance_agent.__main__ import run
from maintenance_agent.application.language_recognition import StaticLanguageRecognizer
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult

from .fakes import FakeConversationHandler, FakeStdinReader


async def test_local_cli_loads_csv_then_receives_mocked_stdin(
    capsys, tmp_path: Path, monkeypatch
) -> None:
    csv_path = Path(__file__).resolve().parents[1] / "fixtures" / "work_orders.csv"
    monkeypatch.setenv("TRACES_DIR", str(tmp_path / "traces"))

    await run(
        csv_path=csv_path,
        stdin_reader=FakeStdinReader(["WO-001|tenant Hola | necesito ayuda"]),
        conversation_handler=FakeConversationHandler(),
        language_recognizer=StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED)
        ),
    )

    captured = capsys.readouterr()
    output = captured.out
    assert captured.err == ""
    assert "WOID:WO-001|ROLE:tenant\n" in output
    assert "WOID:WO-002|ROLE:tenant\n" in output
    assert "Hola | necesito ayuda" not in output
    run_folders = list((tmp_path / "traces" / "runs").iterdir())
    assert len(run_folders) == 1
    events = run_folders[0] / "events.jsonl"
    assert events.exists()
    assert "WO-001" in events.read_text(encoding="utf-8")


async def test_local_cli_answers_unknown_work_order_with_fixed_notice(
    capsys, tmp_path: Path, monkeypatch
) -> None:
    csv_path = Path(__file__).resolve().parents[1] / "fixtures" / "work_orders.csv"
    monkeypatch.setenv("TRACES_DIR", str(tmp_path / "traces"))

    await run(
        csv_path=csv_path,
        stdin_reader=FakeStdinReader(["WO-999|handyman hola"]),
        conversation_handler=FakeConversationHandler(),
        language_recognizer=StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED)
        ),
    )

    assert "WOID:WO-999|ROLE:handyman\nLa orden de trabajo indicada no existe" in (
        capsys.readouterr().out
    )
