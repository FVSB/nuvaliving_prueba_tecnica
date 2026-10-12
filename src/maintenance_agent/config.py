"""Startup-only runtime configuration."""

from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Immutable process settings read once by the composition root."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    anthropic_language_model: str = "claude-haiku-5-5"
    anthropic_conversation_model: str = "claude-haiku-5-5"
    local_timezone: str = "Europe/Madrid"
    traces_dir: Path = Path("traces")
    slot_lookahead_days: int = 7
    slot_daily_start_hour: int = 9
    slot_daily_end_hour: int = 19
    slot_hours: int = 2
    injection_threshold: float = 0.6
    visit_horizon_days: int = 7
    max_message_length: int = 2000

    @field_validator("anthropic_language_model", "anthropic_conversation_model")
    @classmethod
    def validate_anthropic_model(cls, model: str) -> str:
        """Reject empty model names while preserving the configured identifier."""
        if not model.strip():
            raise ValueError("Anthropic model names must not be empty.")
        return model

    @field_validator("injection_threshold")
    @classmethod
    def validate_injection_threshold(cls, threshold: float) -> float:
        """The guard blocks above this self-reported probability, so it must be below 1."""
        if not 0.0 <= threshold < 1.0:
            raise ValueError("INJECTION_THRESHOLD must satisfy 0 <= value < 1.")
        return threshold

    @field_validator("visit_horizon_days", "max_message_length")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        """Both limits only make sense as positive integers."""
        if value < 1:
            raise ValueError("VISIT_HORIZON_DAYS and MAX_MESSAGE_LENGTH must be positive.")
        return value

    @model_validator(mode="after")
    def validate_slot_grid(self) -> "Settings":
        """Require a non-empty presentation grid inside one local day."""
        if self.slot_lookahead_days < 1 or self.slot_hours < 1:
            raise ValueError("SLOT_LOOKAHEAD_DAYS and SLOT_HOURS must be positive.")
        if not 0 <= self.slot_daily_start_hour < self.slot_daily_end_hour <= 24:
            raise ValueError("Slot grid hours must satisfy 0 <= start < end <= 24.")
        if self.slot_daily_start_hour + self.slot_hours > self.slot_daily_end_hour:
            raise ValueError("The slot grid window must fit at least one slot.")
        return self

    @field_validator("local_timezone")
    @classmethod
    def validate_local_timezone(cls, local_timezone: str) -> str:
        """Accept only an installed IANA timezone name."""
        try:
            ZoneInfo(local_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("LOCAL_TIMEZONE must be a valid IANA timezone name.") from error
        return local_timezone
