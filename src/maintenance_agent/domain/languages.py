"""Validated language-recognition vocabulary."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class LanguageCode(StrEnum):
    """Common ISO 639-1 codes plus the safe indeterminate value."""

    SPANISH = "es"
    ENGLISH = "en"
    FRENCH = "fr"
    GERMAN = "de"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    DUTCH = "nl"
    CATALAN = "ca"
    ARABIC = "ar"
    CHINESE = "zh"
    JAPANESE = "ja"
    KOREAN = "ko"
    UNDETERMINED = "undetermined"


class LanguageRecognitionResult(BaseModel):
    """A validated, non-sensitive language classification result."""

    model_config = ConfigDict(frozen=True)

    language_code: LanguageCode

    @classmethod
    def from_provider_value(cls, value: str | None) -> "LanguageRecognitionResult":
        """Convert untrusted provider output to a known code or undetermined."""
        if value is None:
            return cls(language_code=LanguageCode.UNDETERMINED)
        try:
            return cls(language_code=LanguageCode(value.strip().lower()))
        except ValueError:
            return cls(language_code=LanguageCode.UNDETERMINED)
