from datetime import datetime

from maintenance_agent.domain.negotiation import ParticipantRole
from maintenance_agent.prompts.interpret_availability import build_availability_prompt
from maintenance_agent.skills import load_skills, read_skill, skill_index


def test_index_lists_every_skill_without_bodies() -> None:
    index = skill_index()
    assert set(load_skills()) == {"relative-date-phrases", "ambiguity-reasons"}
    assert "- relative-date-phrases:" in index
    assert "Monday and Tuesday" not in index


def test_read_skill_returns_body_or_none() -> None:
    assert "Monday and Tuesday" in read_skill("relative-date-phrases")
    assert read_skill("missing") is None


def test_prompt_injects_index_at_start_of_interpretation() -> None:
    prompt = build_availability_prompt(
        "x", ParticipantRole.TENANT, datetime(2026, 10, 12, 8), "Europe/Madrid"
    )
    assert "read_skill" in prompt and "- ambiguity-reasons:" in prompt
    assert "Monday and Tuesday" not in prompt


def test_skill_markdown_is_declared_as_package_data():
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]
    assert "*.md" in package_data["maintenance_agent.skills"]
