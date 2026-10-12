from pathlib import Path

from maintenance_agent.__main__ import parse_arguments


def test_default_csv_retains_docker_contract() -> None:
    assert parse_arguments([]).csv == Path("/app/work_orders.csv")


def test_local_csv_path_can_be_selected() -> None:
    assert parse_arguments(["--csv", "./work_orders.csv"]).csv == Path("work_orders.csv")
