"""Versioned business rules loaded once at startup from a JSON file shipped in the image."""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maintenance_agent.config import Settings
from maintenance_agent.domain.work_orders import Urgency


class LocalizedText(BaseModel):
    """A message keyed by language code; both supported languages are required."""

    model_config = ConfigDict(frozen=True)

    es: str = Field(min_length=1)
    en: str = Field(min_length=1)

    def for_language(self, language: str) -> str:
        """Unknown languages fall back to English, as the hardcoded messages did."""
        return {"es": self.es, "en": self.en}.get(language, self.en)


class Messages(BaseModel):
    model_config = ConfigDict(frozen=True)

    retry_reminder: LocalizedText
    proposal_withdrawn: LocalizedText


class BusinessRules(BaseModel):
    """Policy and message text that operators review in a PR instead of editing code."""

    model_config = ConfigDict(frozen=True)

    urgency_rank: dict[str, int]
    no_response_retries_enabled: bool = False
    messages: Messages

    @model_validator(mode="after")
    def validate_urgency_covers_every_level(self) -> "BusinessRules":
        """Every work-order urgency needs a rank, otherwise scheduling would fail at runtime."""
        missing = {urgency.value for urgency in Urgency} - set(self.urgency_rank)
        if missing:
            raise ValueError(f"urgency_rank is missing levels: {sorted(missing)}")
        return self


def load_business_rules(path: Path) -> BusinessRules:
    """Read and validate the rules file; a bad file must stop startup, never run with defaults."""
    return BusinessRules.model_validate_json(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def active_rules() -> BusinessRules:
    """The one rules object per process, read from BUSINESS_RULES_PATH (shipped in the image)."""
    return load_business_rules(Settings().business_rules_path)
