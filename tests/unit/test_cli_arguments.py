from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from maintenance_agent.__main__ import parse_arguments
from maintenance_agent.config import Settings


def test_default_csv_comes_from_settings_so_docker_contract_holds() -> None:
    # No CLI default: Settings owns the path (WORK_ORDERS_CSV_PATH, /app/work_orders.csv by default).
    assert parse_arguments([]).csv is None
    assert Settings.model_fields["work_orders_csv_path"].default == Path("/app/work_orders.csv")


def test_local_csv_path_can_be_selected() -> None:
    assert parse_arguments(["--csv", "./work_orders.csv"]).csv == Path("work_orders.csv")


def test_now_defaults_to_the_real_clock() -> None:
    assert parse_arguments([]).now is None


def test_now_accepts_an_iso_timestamp_with_offset() -> None:
    now = parse_arguments(["--now", "2026-10-12T12:00:00+02:00"]).now
    assert now == datetime(2026, 10, 12, 12, 0, tzinfo=timezone(timedelta(hours=2)))


@pytest.mark.parametrize("value", ["2026-10-12T12:00", "not-a-date", "2026-02-30T10:00+02:00"])
def test_now_rejects_naive_or_invalid_timestamps(value: str) -> None:
    with pytest.raises(SystemExit):
        parse_arguments(["--now", value])
