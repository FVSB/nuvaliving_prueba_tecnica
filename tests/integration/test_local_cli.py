from pathlib import Path

from maintenance_agent.__main__ import run

from .fakes import FakeStdinReader


async def test_local_cli_loads_csv_then_receives_mocked_stdin(capsys) -> None:
    csv_path = Path(__file__).resolve().parents[1] / "fixtures" / "work_orders.csv"

    await run(
        csv_path=csv_path,
        stdin_reader=FakeStdinReader(["WO-001|tenant Hola | necesito ayuda"]),
    )

    output = capsys.readouterr().out
    assert "WOID:WO-001|ROLE:tenant\nNueva orden de trabajo iniciada.\n\n" in output
    assert "WOID:WO-002|ROLE:tenant\nNueva orden de trabajo iniciada.\n\n" in output
    assert output.endswith("WOID:WO-001|ROLE:tenant\nHola | necesito ayuda\n\n")
