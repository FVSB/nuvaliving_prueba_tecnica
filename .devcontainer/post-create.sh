#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Fresh named volumes may be owned by root; preserve contents and grant the remote user access.
sudo mkdir -p "$CODEX_HOME" "$CLAUDE_CONFIG_DIR" "$GOPATH"
sudo chown -R "$(id -u):$(id -g)" "$CODEX_HOME" "$CLAUDE_CONFIG_DIR" "$GOPATH"

# Locked Node tools; named-volume agent homes are never overwritten.
npm ci --prefix .devcontainer
sudo ln -sfn "$PWD/.devcontainer/node_modules/.bin/codex" /usr/local/bin/codex
# The published CodeGraph npm shim resolves the matching prebuilt bundle.
sudo ln -sfn "$PWD/.devcontainer/node_modules/.bin/codegraph" /usr/local/bin/codegraph

while IFS= read -r tool; do
  [[ -z "$tool" || "$tool" == \#* ]] && continue
  go install "$tool"
done < .devcontainer/go-tools.txt

# Never reuse the host's .venv; the container uses a separate named volume.
sudo mkdir -p "$UV_PROJECT_ENVIRONMENT"
sudo chown -R "$(id -u):$(id -g)" "$(dirname "$UV_PROJECT_ENVIRONMENT")"
uv sync --frozen --all-groups

python .devcontainer/configure-mcp.py

# Register MCP without initializing/deleting the shared CodeGraph database.
codegraph install --target codex,claude --location global --yes --no-permissions
printf '\nDevelopment tools ready:\n'
python --version
uv --version
codex --version
codegraph --version
engram version
printf '\nRun bash .devcontainer/setup-agents.sh once for Engram hooks and agent login.\n'
