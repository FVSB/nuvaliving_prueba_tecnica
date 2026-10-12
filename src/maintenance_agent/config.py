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

    @field_validator("anthropic_language_model", "anthropic_conversation_model")
    @classmethod
    def validate_anthropic_model(cls, model: str) -> str:
        """Reject empty model names while preserving the configured identifier."""
        if not model.strip():
            raise ValueError("Anthropic model names must not be empty.")
        return model

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
