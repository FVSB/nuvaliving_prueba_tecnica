"""CLI entry point for local and container execution."""

import argparse
import asyncio
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from maintenance_agent.application.conversation import ConversationHandler
from maintenance_agent.application.injection_guard import InjectionGuard
from maintenance_agent.application.language_recognition import LanguageRecognizer
from maintenance_agent.bootstrap import build_container

if TYPE_CHECKING:
    from maintenance_agent.application.coordinator import InboundReader


def _aware_timestamp(value: str) -> datetime:
    """Parse an ISO timestamp that carries a UTC offset."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid ISO timestamp: {value!r}") from error
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(f"timestamp needs a UTC offset: {value!r}")
    return parsed


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Allow local CSV selection while retaining the binding Docker default."""
    parser = argparse.ArgumentParser(description="Async work-order coordination")
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="CSV input path (default: WORK_ORDERS_CSV_PATH, /app/work_orders.csv in Docker)",
    )
    parser.add_argument(
        "--now",
        type=_aware_timestamp,
        default=None,
        help="Freeze the business clock at an ISO timestamp with offset, for reproducible runs",
    )
    return parser.parse_args(argv)


async def run(
    csv_path: Path | None = None,
    stdin_reader: "InboundReader | None" = None,
    conversation_handler: ConversationHandler | None = None,
    language_recognizer: LanguageRecognizer | None = None,
    now: datetime | None = None,
    injection_guard: InjectionGuard | None = None,
) -> None:
    """Load work orders and start asynchronous live message coordination."""
    container = build_container(csv_path=csv_path, now=now)
    if stdin_reader is not None:
        container.stdin_reader.override(stdin_reader)
    if conversation_handler is not None:
        container.conversation_handler.override(conversation_handler)
        # An injected conversation handler means no real LLM: use the given guard or none.
        container.injection_guard.override(injection_guard)
    elif injection_guard is not None:
        container.injection_guard.override(injection_guard)
    if language_recognizer is not None:
        container.language_recognizer.override(language_recognizer)
    container.runtime_writer().write(event_type="csv_read_start", detail={})
    work_orders = await container.csv_work_order_reader().read()
    container.runtime_writer().write(
        event_type="csv_read_complete", detail={"count": len(work_orders)}
    )
    container.events_writer().write(
        event_type="work_orders_loaded", detail={"count": len(work_orders)}
    )
    coordinator = container.coordinator()
    container.events_writer().write(event_type="coordinator_ready", detail={})
    await coordinator.run(work_orders)


def main() -> None:
    """Run the async coordinator from the installed console script."""
    arguments = parse_arguments()
    asyncio.run(run(csv_path=arguments.csv, now=arguments.now))


if __name__ == "__main__":
    main()
