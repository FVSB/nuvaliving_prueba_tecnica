"""Preserve workspace MCP entries while binding Engram to the shared project store."""

import json
from pathlib import Path


def configure(workspace: Path) -> None:
    """Update only the managed workspace Engram connection."""
    path = workspace / ".mcp.json"
    config = json.loads(path.read_text()) if path.exists() else {}
    servers = config.setdefault("mcpServers", {})
    engram = servers.setdefault("engram", {})
    engram.update(type="stdio", command="engram", args=["mcp", "--tools=agent"])
    env = engram.setdefault("env", {})
    env.update(ENGRAM_DATA_DIR=str(workspace / ".engram-data"), ENGRAM_PROJECT="nuvaliving_test")
    path.write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    configure(Path(__file__).resolve().parent.parent)
