"""Run-scoped JSONL trace writer per the architecture contract."""

import json
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class RunContext:
    """One isolated execution under /app/traces/runs/."""

    run_id: str
    folder: Path

    @property
    def manifest_path(self) -> Path:
        """Return the manifest.jsonl path inside this run folder."""
        return self.folder / "manifest.jsonl"

    @property
    def events_path(self) -> Path:
        """Return the events.jsonl path inside this run folder."""
        return self.folder / "events.jsonl"

    @property
    def runtime_path(self) -> Path:
        """Return the runtime.jsonl path inside this run folder."""
        return self.folder / "runtime.jsonl"


def build_run_context(traces_dir: Path, now: datetime, tz: ZoneInfo) -> RunContext:
    """Create the run folder using a Madrid timestamp and a unique run id."""
    madrid_now = now.astimezone(tz)
    stamp = madrid_now.strftime("%Y%m%dT%H%M%S")
    offset = madrid_now.strftime("%z")
    formatted_offset = f"{offset[:3]}:{offset[3:]}" if offset else "+00:00"
    run_id = uuid.uuid4().hex[:8]
    folder = traces_dir / "runs" / f"{stamp}{formatted_offset}-{run_id}"
    folder.mkdir(parents=True, exist_ok=True)
    return RunContext(run_id=run_id, folder=folder)


class TraceWriter:
    """Append one JSON object per line to a single file with a monotonic sequence."""

    def __init__(self, path: Path, run_id: str, tz: ZoneInfo) -> None:
        self._path = path
        self._run_id = run_id
        self._tz = tz
        self._lock = threading.Lock()
        self._sequence = 0
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.touch()

    @property
    def path(self) -> Path:
        """Return the file this writer appends to."""
        return self._path

    def write(
        self,
        *,
        event_type: str,
        detail: Mapping[str, Any],
        work_order_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Append one event with timestamp, sequence, work-order id, type, and detail."""
        with self._lock:
            self._sequence += 1
            record = {
                "run_id": self._run_id,
                "sequence": self._sequence,
                "timestamp": (timestamp or datetime.now(self._tz)).isoformat(),
                "scope": "work_order" if work_order_id is not None else "application",
                "work_order_id": work_order_id,
                "event_type": event_type,
                "detail": dict(detail),
            }
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
