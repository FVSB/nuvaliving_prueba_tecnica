"""The sole composition root for the process."""

from pathlib import Path

from maintenance_agent.config import Settings
from maintenance_agent.dependencies import Container


def build_container(csv_path: Path = Path("/app/work_orders.csv")) -> Container:
    """Read configuration once and return fully wired dependencies."""
    settings = Settings()
    container = Container()
    container.settings.override(settings)
    container.csv_path.override(csv_path)
    return container
