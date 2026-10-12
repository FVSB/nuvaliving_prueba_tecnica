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
