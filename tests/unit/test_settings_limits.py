import pytest
from pydantic import ValidationError

from maintenance_agent.config import Settings


def test_limits_default_to_a_week_and_two_thousand_characters() -> None:
    settings = Settings(_env_file=None)
    assert settings.visit_horizon_days == 7
    assert settings.max_message_length == 2000


def test_limits_come_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("VISIT_HORIZON_DAYS", "30")
    monkeypatch.setenv("MAX_MESSAGE_LENGTH", "500")
    settings = Settings(_env_file=None)
    assert (settings.visit_horizon_days, settings.max_message_length) == (30, 500)


@pytest.mark.parametrize("name", ["VISIT_HORIZON_DAYS", "MAX_MESSAGE_LENGTH"])
def test_limits_must_be_positive(monkeypatch, name: str) -> None:
    monkeypatch.setenv(name, "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_every_setting_but_the_api_key_has_a_default_without_dotenv(monkeypatch) -> None:
    for name in list(__import__("os").environ):
        if name.isupper() and name.startswith(
            ("ANTHROPIC_", "NO_RESPONSE_", "SLOT_", "LOCAL_", "TRACES_", "VISIT_", "MAX_", "INJ")
        ):
            monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.anthropic_api_key is None  # the only setting that may stay unset
    assert settings.no_response_retry_wait_seconds == 300
    assert settings.no_response_max_retries == 3
    assert settings.no_response_poll_seconds == 10


def test_no_response_retry_settings_come_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("NO_RESPONSE_RETRY_WAIT_SECONDS", "45.5")
    monkeypatch.setenv("NO_RESPONSE_MAX_RETRIES", "0")
    monkeypatch.setenv("NO_RESPONSE_POLL_SECONDS", "2")
    settings = Settings(_env_file=None)
    assert settings.no_response_retry_wait_seconds == 45.5
    assert settings.no_response_max_retries == 0
    assert settings.no_response_poll_seconds == 2


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("NO_RESPONSE_RETRY_WAIT_SECONDS", "0"),
        ("NO_RESPONSE_POLL_SECONDS", "-1"),
        ("NO_RESPONSE_MAX_RETRIES", "-1"),
    ],
)
def test_no_response_retry_settings_reject_invalid_values(monkeypatch, name, value) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
