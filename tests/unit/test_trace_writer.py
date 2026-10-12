"""Unit tests for the JSONL trace writer and run-context builder."""

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from maintenance_agent.infrastructure.trace_writer import (
    RunContext,
    TraceWriter,
    build_run_context,
)


def _writer(path: Path) -> TraceWriter:
    return TraceWriter(path, "test-run", ZoneInfo("Europe/Madrid"))


def test_trace_writer_appends_one_json_object_per_line(tmp_path: Path) -> None:
    writer = _writer(tmp_path / "events.jsonl")

    writer.write(event_type="a", detail={"x": 1}, work_order_id="WO-1")
    writer.write(event_type="b", detail={"y": 2}, work_order_id="WO-2")

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["sequence"] == 1
    assert first["run_id"] == "test-run"
    assert first["scope"] == "work_order"
    assert first["event_type"] == "a"
    assert first["work_order_id"] == "WO-1"
    assert first["detail"] == {"x": 1}
    assert second["sequence"] == 2
    assert second["event_type"] == "b"


def test_trace_writer_assigns_monotonic_sequence(tmp_path: Path) -> None:
    writer = _writer(tmp_path / "events.jsonl")

    for index in range(5):
        writer.write(event_type=str(index), detail={"i": index})

    sequences = [
        json.loads(line)["sequence"]
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert sequences == [1, 2, 3, 4, 5]


def test_trace_writer_uses_supplied_timestamp_in_iso_format(tmp_path: Path) -> None:
    writer = _writer(tmp_path / "events.jsonl")
    stamp = datetime(2026, 10, 12, 9, 15, tzinfo=timezone.utc)

    writer.write(event_type="a", detail={}, timestamp=stamp)

    record = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert record["timestamp"] == "2026-10-12T09:15:00+00:00"


def test_trace_writer_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "runs" / "events.jsonl"

    _writer(nested)

    assert nested.parent.exists()


def test_build_run_context_creates_unique_folder_with_madrid_stamp(tmp_path: Path) -> None:
    madrid = ZoneInfo("Europe/Madrid")
    now = datetime(2026, 10, 12, 9, 15, tzinfo=timezone.utc)

    context = build_run_context(tmp_path, now, madrid)

    assert context.folder.parent == tmp_path / "runs"
    assert context.folder.name.startswith("20261012T1115")
    assert "+02:00" in context.folder.name or "+01:00" in context.folder.name
    assert len(context.run_id) == 8
    assert context.events_path == context.folder / "events.jsonl"
    assert context.manifest_path == context.folder / "manifest.jsonl"
    assert context.runtime_path == context.folder / "runtime.jsonl"


def test_run_context_paths_under_folder() -> None:
    context = RunContext(run_id="abc", folder=Path("/tmp/runs/x"))

    assert context.events_path == Path("/tmp/runs/x/events.jsonl")
    assert context.manifest_path == Path("/tmp/runs/x/manifest.jsonl")
    assert context.runtime_path == Path("/tmp/runs/x/runtime.jsonl")
