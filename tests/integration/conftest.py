import json
from pathlib import Path

import pytest

from maintenance_agent.business_rules import active_rules

RULES = Path(__file__).resolve().parents[2] / "config" / "business_rules.json"


@pytest.fixture
def retries_enabled(tmp_path, monkeypatch):
    """Business rules with no_response_retries_enabled=true; the shipped default is false."""
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    rules["no_response_retries_enabled"] = True
    path = tmp_path / "business_rules.json"
    path.write_text(json.dumps(rules), encoding="utf-8")
    monkeypatch.setenv("BUSINESS_RULES_PATH", str(path))
    active_rules.cache_clear()
    yield
    active_rules.cache_clear()
