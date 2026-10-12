"""The sole composition root for the process."""

import logging
from pathlib import Path

from anthropic import AsyncAnthropic

from maintenance_agent.application.language_recognition import StaticLanguageRecognizer
from maintenance_agent.config import Settings
from maintenance_agent.dependencies import Container
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.infrastructure.anthropic_language_recognizer import (
    AnthropicLanguageRecognizer,
)


def _configure_logging() -> None:
    """Emit startup language codes to stderr without touching the protocol stream."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def build_container(csv_path: Path = Path("/app/work_orders.csv")) -> Container:
    """Read settings once and return fully wired dependencies."""
    _configure_logging()
    settings = Settings()
    container = Container()
    container.settings.override(settings)
    container.csv_path.override(csv_path)

    if settings.anthropic_api_key is None:
        recognizer = StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED)
        )
    else:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
        recognizer = AnthropicLanguageRecognizer(client)
    container.language_recognizer.override(recognizer)
    return container
