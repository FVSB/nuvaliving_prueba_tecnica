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
    anthropic_injection_model: str = "claude-haiku-5-5"
    local_timezone: str = "Europe/Madrid"
    traces_dir: Path = Path("traces")
    work_orders_csv_path: Path = Path("/app/work_orders.csv")
    business_rules_path: Path = Path("config/business_rules.json")
    slot_lookahead_days: int = 7
    slot_daily_start_hour: int = 9
    slot_daily_end_hour: int = 19
    slot_hours: int = 2
    injection_threshold: float = 0.6
    visit_horizon_days: int = 7
    max_message_length: int = 2000
    no_response_retry_wait_seconds: float = 300.0
    no_response_max_retries: int = 3
    no_response_poll_seconds: float = 10.0

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

    @field_validator(
        "visit_horizon_days",
        "max_message_length",
    )
    @classmethod
    def validate_positive(cls, value: int) -> int:
        """Limits only make sense as positive integers."""
        if value < 1:
            raise ValueError("Positive integer limits must be at least 1.")
        return value

    @field_validator("anthropic_injection_model")
    @classmethod
    def validate_injection_model(cls, model: str) -> str:
        """Same rule as the other Anthropic model identifiers."""
        if not model.strip():
            raise ValueError("Anthropic model names must not be empty.")
        return model

    @field_validator("no_response_retry_wait_seconds", "no_response_poll_seconds")
    @classmethod
    def validate_positive_seconds(cls, value: float) -> float:
        """Waiting and polling intervals only make sense as positive durations."""
        if value <= 0:
            raise ValueError(
                "NO_RESPONSE_RETRY_WAIT_SECONDS and NO_RESPONSE_POLL_SECONDS must be positive."
            )
        return value

    @field_validator("no_response_max_retries")
    @classmethod
    def validate_non_negative_retries(cls, value: int) -> int:
        """Zero retries closes on the first expiry; negative values are meaningless."""
        if value < 0:
            raise ValueError("NO_RESPONSE_MAX_RETRIES must not be negative.")
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
