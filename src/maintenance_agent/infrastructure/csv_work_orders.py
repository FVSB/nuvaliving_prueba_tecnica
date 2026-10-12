"""Asynchronous adapter for the binding work-order CSV."""

import asyncio
import csv
from collections.abc import Sequence
from pathlib import Path

from maintenance_agent.domain.work_orders import WorkOrder


class CsvWorkOrderReader:
    """Read and validate the mounted CSV once during application startup."""

    def __init__(self, local_timezone: str, path: Path = Path("/app/work_orders.csv")) -> None:
        self._local_timezone = local_timezone
        self._path = path

    async def read(self) -> Sequence[WorkOrder]:
        """Read outside the event loop, then return normalized work orders."""
        return await asyncio.to_thread(self._read_synchronously)

    def _read_synchronously(self) -> list[WorkOrder]:
        with self._path.open(encoding="utf-8", newline="") as csv_file:
            return [
                WorkOrder.model_validate(row, context={"local_timezone": self._local_timezone})
                for row in csv.DictReader(csv_file)
            ]
