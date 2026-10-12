#!/usr/bin/env bash
set -euo pipefail

command -v engram >/dev/null || { echo "engram is missing; rebuild the dev container first." >&2; exit 1; }
command -v codex >/dev/null || { echo "codex is missing; rebuild the dev container first." >&2; exit 1; }
command -v claude >/dev/null || { echo "claude is missing; rebuild the dev container first." >&2; exit 1; }

# Installs Engram's agent integrations. Claude's setup may ask whether to allow
# its memory tools; run this script in an interactive container terminal.
engram setup codex
engram setup claude-code

echo "Engram integrations configured. Restart Codex and Claude Code."
