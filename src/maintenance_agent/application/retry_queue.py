"""Heap of orders waiting for a silent participant, keyed by the UTC time they were placed."""

import heapq
import itertools
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class RetryEntry:
    """One order in the RETRYING state: who stayed silent and how many retries were sent."""

    work_order_id: str
    role: str
    attempt: int
    placed_at: datetime


class NoResponseRetryQueue:
    """Min-heap on the UTC placement time; an entry is due once `wait` has elapsed since it.

    Cancelling is lazy: the order's live entry is forgotten and stale heap items are skipped.
    The clock is the real UTC clock, never the frozen business clock.
    """

    def __init__(
        self,
        wait_seconds: float,
        max_retries: int,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._wait = timedelta(seconds=wait_seconds)
        self._max_retries = max_retries
        self._clock = clock
        self._heap: list[tuple[datetime, int, str]] = []
        self._live: dict[str, tuple[int, RetryEntry]] = {}
        self._counter = itertools.count()

    @property
    def max_retries(self) -> int:
        return self._max_retries

    def schedule(self, work_order_id: str, role: str, attempt: int = 0) -> RetryEntry:
        """Place (or re-place) the order; any earlier entry for it becomes stale."""
        entry = RetryEntry(work_order_id, role, attempt, self._clock())
        token = next(self._counter)
        self._live[work_order_id] = (token, entry)
        heapq.heappush(self._heap, (entry.placed_at, token, work_order_id))
        return entry

    def is_pending(self, work_order_id: str) -> bool:
        return work_order_id in self._live

    def role_of(self, work_order_id: str) -> str | None:
        live = self._live.get(work_order_id)
        return live[1].role if live else None

    def cancel(self, work_order_id: str) -> bool:
        return self._live.pop(work_order_id, None) is not None

    def pop_due(self) -> list[RetryEntry]:
        """Remove and return every live entry whose wait has elapsed, oldest first."""
        now = self._clock()
        due: list[RetryEntry] = []
        while self._heap and self._heap[0][0] + self._wait <= now:
            _, token, work_order_id = heapq.heappop(self._heap)
            live = self._live.get(work_order_id)
            if live is not None and live[0] == token:
                del self._live[work_order_id]
                due.append(live[1])
        return due

    def drain(self) -> list[RetryEntry]:
        """Remove and return every live entry regardless of time (input ended)."""
        entries = [entry for _, entry in sorted(self._live.values(), key=lambda it: it[0])]
        self._live.clear()
        self._heap.clear()
        return entries

    def exhausted(self, entry: RetryEntry) -> bool:
        """True when all retries were sent and the last wait elapsed: close the order."""
        return entry.attempt >= self._max_retries
