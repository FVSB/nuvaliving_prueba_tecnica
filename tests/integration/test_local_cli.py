from pathlib import Path

from maintenance_agent.__main__ import run

from .fakes import FakeStdinReader


async def test_local_cli_loads_csv_then_receives_mocked_stdin(
    capsys, tmp_path: Path, monkeypatch
) -> None:
    csv_path = Path(__file__).resolve().parents[1] / "fixtures" / "work_orders.csv"
    monkeypatch.setenv("TRACES_DIR", str(tmp_path / "traces"))

    await run(
        csv_path=csv_path,
        stdin_reader=FakeStdinReader(["WO-001|tenant Hola | necesito ayuda"]),
    )

    captured = capsys.readouterr()
    output = captured.out
    assert captured.err == ""
    assert "WOID:WO-001|ROLE:tenant\nNueva orden de trabajo iniciada.\n\n" in output
    assert "WOID:WO-002|ROLE:tenant\nNueva orden de trabajo iniciada.\n\n" in output
    assert output.endswith("WOID:WO-001|ROLE:tenant\nHola | necesito ayuda\n\n")
    run_folders = list((tmp_path / "traces" / "runs").iterdir())
    assert len(run_folders) == 1
    events = run_folders[0] / "events.jsonl"
    assert events.exists()
    assert "WO-001" in events.read_text(encoding="utf-8")
