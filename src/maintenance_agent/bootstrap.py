"""The sole composition root for the process."""

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropic

from maintenance_agent.application.language_recognition import StaticLanguageRecognizer
from maintenance_agent.config import Settings
from maintenance_agent.dependencies import Container
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.infrastructure.anthropic_language_recognizer import (
    AnthropicLanguageRecognizer,
)
from maintenance_agent.infrastructure.trace_writer import (
    RunContext,
    TraceWriter,
    build_run_context,
)


def _effective_snapshot(settings: Settings, run_context: RunContext) -> dict[str, str]:
    """Build the manifest snapshot without ever leaking the Anthropic credential."""
    snapshot = {
        "local_timezone": settings.local_timezone,
        "traces_dir": str(settings.traces_dir),
        "anthropic_adapter": "static" if settings.anthropic_api_key is None else "anthropic",
    }
    snapshot["run_id"] = run_context.run_id
    return snapshot


def build_container(csv_path: Path = Path("/app/work_orders.csv")) -> Container:
    """Read settings once, create one run folder, and return fully wired dependencies."""
    settings = Settings()
    madrid = ZoneInfo(settings.local_timezone)

    run_context = build_run_context(
        traces_dir=settings.traces_dir,
        now=datetime.now(timezone.utc),
        tz=madrid,
    )
    manifest_writer = TraceWriter(run_context.manifest_path, run_context.run_id, madrid)
    events_writer = TraceWriter(run_context.events_path, run_context.run_id, madrid)
    runtime_writer = TraceWriter(run_context.runtime_path, run_context.run_id, madrid)
    manifest_writer.write(
        event_type="run_started",
        detail={"snapshot": _effective_snapshot(settings, run_context)},
    )

    container = Container()
    container.settings.override(settings)
    container.csv_path.override(csv_path)
    container.run_context.override(run_context)
    container.manifest_writer.override(manifest_writer)
    container.events_writer.override(events_writer)
    container.runtime_writer.override(runtime_writer)

    if settings.anthropic_api_key is None:
        recognizer = StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED)
        )
    else:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
        recognizer = AnthropicLanguageRecognizer(client)
    container.language_recognizer.override(recognizer)
    return container
