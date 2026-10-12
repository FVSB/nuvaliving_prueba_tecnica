"""Startup-only runtime configuration."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Immutable process settings read once by the composition root."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    local_timezone: str = "Europe/Madrid"

    @field_validator("local_timezone")
    @classmethod
    def validate_local_timezone(cls, local_timezone: str) -> str:
        """Accept only an installed IANA timezone name."""
        try:
            ZoneInfo(local_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("LOCAL_TIMEZONE must be a valid IANA timezone name.") from error
        return local_timezone
