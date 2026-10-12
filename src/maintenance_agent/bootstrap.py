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

_QUIET_THIRD_PARTY_LOGGERS = ("httpx", "httpcore", "anthropic")


def _configure_logging(level_name: str) -> None:
    """Keep stderr quiet by default; emit structured records only when the operator opts in."""
    level = getattr(logging, level_name.upper(), logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )
    for logger_name in _QUIET_THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def build_container(csv_path: Path = Path("/app/work_orders.csv")) -> Container:
    """Read settings once and return fully wired dependencies."""
    settings = Settings()
    _configure_logging(settings.log_level)
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
