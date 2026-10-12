from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult


def test_catalogue_contains_required_common_iso_codes() -> None:
    required_codes = {
        LanguageCode.SPANISH,
        LanguageCode.ENGLISH,
        LanguageCode.FRENCH,
        LanguageCode.GERMAN,
    }
    assert required_codes <= set(LanguageCode)
    assert LanguageCode.UNDETERMINED.value == "undetermined"


def test_unknown_provider_value_becomes_undetermined() -> None:
    result = LanguageRecognitionResult.from_provider_value("invalid-code")

    assert result.language_code is LanguageCode.UNDETERMINED
