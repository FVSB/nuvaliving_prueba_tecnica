#!/usr/bin/env bash
set -euo pipefail

if ! command -v codex >/dev/null 2>&1; then
  npm install --global @openai/codex
fi

if ! command -v engram >/dev/null 2>&1; then
  go install github.com/Gentleman-Programming/engram/v3/cmd/engram@v3.3.2
fi

printf '\nTools ready:\n'
codex --version
claude --version
engram version
printf '\nRun .devcontainer/setup-agents.sh once to connect Engram plugins and session hooks.\n'
