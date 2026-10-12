"""Unit tests for the startup logging configuration."""

import logging

import pytest

from maintenance_agent.bootstrap import _configure_logging


@pytest.fixture(autouse=True)
def _reset_root_logger() -> None:
    """Ensure each test starts from a clean stdlib logging state."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(logging.NOTSET)
    for name in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(name).setLevel(logging.NOTSET)
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(logging.NOTSET)


def test_configure_logging_defaults_to_quiet_root() -> None:
    _configure_logging("WARNING")

    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_silences_third_party_loggers() -> None:
    _configure_logging("WARNING")

    for name in ("httpx", "httpcore", "anthropic"):
        assert logging.getLogger(name).level == logging.WARNING


def test_configure_logging_elevates_root_when_requested() -> None:
    _configure_logging("INFO")

    assert logging.getLogger().level == logging.INFO
    for name in ("httpx", "httpcore", "anthropic"):
        assert logging.getLogger(name).level == logging.WARNING


def test_configure_logging_accepts_lowercase_level_names() -> None:
    _configure_logging("debug")

    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_falls_back_to_warning_for_unknown_levels() -> None:
    _configure_logging("not-a-level")

    assert logging.getLogger().level == logging.WARNING