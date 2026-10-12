from maintenance_agent.prompts.language_recognition import build_language_recognition_prompt


def test_prompt_is_english_and_lists_allowed_values() -> None:
    prompt = build_language_recognition_prompt("Water is leaking under the sink.")

    assert "Identify the language" in prompt
    assert "undetermined" in prompt
    assert "es" in prompt
    assert "Water is leaking under the sink." in prompt
