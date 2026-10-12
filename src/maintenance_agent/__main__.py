"""CLI entry point for local and container execution."""

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from maintenance_agent.bootstrap import build_container

if TYPE_CHECKING:
    from maintenance_agent.application.coordinator import InboundReader


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Allow local CSV selection while retaining the binding Docker default."""
    parser = argparse.ArgumentParser(description="Async work-order coordination")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("/app/work_orders.csv"),
        help="CSV input path (default: /app/work_orders.csv)",
    )
    return parser.parse_args(argv)


async def run(
    csv_path: Path = Path("/app/work_orders.csv"),
    stdin_reader: "InboundReader | None" = None,
) -> None:
    """Load work orders and start asynchronous live message coordination."""
    container = build_container(csv_path=csv_path)
    if stdin_reader is not None:
        container.stdin_reader.override(stdin_reader)
    work_orders = await container.csv_work_order_reader().read()
    await container.coordinator().run(work_orders)


def main() -> None:
    """Run the async coordinator from the installed console script."""
    arguments = parse_arguments()
    asyncio.run(run(csv_path=arguments.csv))


if __name__ == "__main__":
    main()
