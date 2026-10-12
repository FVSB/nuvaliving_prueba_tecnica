from datetime import datetime, timedelta, timezone

from maintenance_agent.application.retry_queue import NoResponseRetryQueue

T0 = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _queue(clock: Clock, wait: float = 60, retries: int = 3) -> NoResponseRetryQueue:
    return NoResponseRetryQueue(wait, retries, clock)


def test_entry_is_due_only_after_the_wait_since_it_was_placed() -> None:
    clock = Clock()
    queue = _queue(clock)
    queue.schedule("WO-1", "tenant")
    clock.advance(59)
    assert queue.pop_due() == []
    clock.advance(1)
    [entry] = queue.pop_due()
    assert (entry.work_order_id, entry.role, entry.attempt) == ("WO-1", "tenant", 0)
    assert entry.placed_at == T0
    assert not queue.is_pending("WO-1")


def test_oldest_placement_comes_out_first() -> None:
    clock = Clock()
    queue = _queue(clock)
    queue.schedule("WO-1", "tenant")
    clock.advance(10)
    queue.schedule("WO-2", "handyman")
    clock.advance(100)
    assert [e.work_order_id for e in queue.pop_due()] == ["WO-1", "WO-2"]


def test_rescheduling_replaces_the_earlier_entry() -> None:
    clock = Clock()
    queue = _queue(clock)
    queue.schedule("WO-1", "tenant")
    clock.advance(50)
    queue.schedule("WO-1", "tenant", attempt=1)
    clock.advance(30)  # the first placement would be due, the second is not
    assert queue.pop_due() == []
    clock.advance(30)
    [entry] = queue.pop_due()
    assert entry.attempt == 1


def test_cancel_drops_the_entry_without_returning_it() -> None:
    clock = Clock()
    queue = _queue(clock)
    queue.schedule("WO-1", "tenant")
    assert queue.cancel("WO-1") is True
    assert queue.cancel("WO-1") is False
    clock.advance(1000)
    assert queue.pop_due() == []


def test_exhausted_after_the_configured_retries() -> None:
    queue = _queue(Clock(), retries=3)
    assert [queue.exhausted(queue.schedule("WO-1", "tenant", n)) for n in range(4)] == [
        False,
        False,
        False,
        True,
    ]


def test_drain_returns_everything_pending_regardless_of_time() -> None:
    queue = _queue(Clock())
    queue.schedule("WO-1", "tenant")
    queue.schedule("WO-2", "handyman")
    assert [e.work_order_id for e in queue.drain()] == ["WO-1", "WO-2"]
    assert queue.drain() == []
