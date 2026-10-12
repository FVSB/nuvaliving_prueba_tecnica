"""Progressive-disclosure agent skills: an index is always injected, bodies are read on demand."""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    body: str


@cache
def load_skills() -> dict[str, Skill]:
    """Parse every `*.md` skill file: `name:` and `description:` frontmatter, then the body."""
    skills: dict[str, Skill] = {}
    for path in sorted(_DIR.glob("*.md")):
        _, header, body = path.read_text(encoding="utf-8").split("---", 2)
        meta = dict(line.split(":", 1) for line in header.strip().splitlines() if ":" in line)
        name = meta["name"].strip()
        skills[name] = Skill(name, meta["description"].strip(), body.strip())
    return skills


def skill_index() -> str:
    """The always-injected catalogue: one line per skill, no bodies."""
    return "\n".join(f"- {s.name}: {s.description}" for s in load_skills().values())


def read_skill(name: str) -> str | None:
    skill = load_skills().get(name)
    return skill.body if skill else None
