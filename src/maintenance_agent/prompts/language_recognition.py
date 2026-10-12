"""English-only language-recognition prompt builder."""

from maintenance_agent.domain.languages import LanguageCode

_ALLOWED_CODES = ", ".join(code.value for code in LanguageCode)


def build_language_recognition_prompt(description: str) -> str:
    """Build the constrained prompt without retaining it in workflow state."""
    return (
        "Identify the language of the work-order description. "
        f"Return exactly one of these ISO 639-1 codes: {_ALLOWED_CODES}. "
        "Return undetermined when the description is empty, ambiguous, mixed, unsupported, "
        "or lacks reliable language evidence. Do not add explanations.\n\n"
        f"Description:\n{description}"
    )
