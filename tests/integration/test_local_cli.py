import subprocess
import sys
from pathlib import Path


def test_local_cli_loads_csv_then_receives_stdin() -> None:
    csv_path = Path(__file__).resolve().parents[1] / "fixtures" / "work_orders.csv"
    result = subprocess.run(
        [sys.executable, "-m", "maintenance_agent", "--csv", str(csv_path)],
        input="WO-001|tenant Hola | necesito ayuda\n",
        text=True,
        capture_output=True,
        timeout=15,
        check=True,
    )
    assert result.stderr == ""
    assert "WOID:WO-001|ROLE:tenant\nNueva orden de trabajo iniciada.\n\n" in result.stdout
    assert "WOID:WO-002|ROLE:tenant\nNueva orden de trabajo iniciada.\n\n" in result.stdout
    assert result.stdout.endswith("WOID:WO-001|ROLE:tenant\nHola | necesito ayuda\n\n")
