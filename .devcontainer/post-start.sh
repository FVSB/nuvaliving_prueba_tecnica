#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# Installs newly registered Python dependencies after a stop/start as well as a rebuild.
uv sync --frozen --all-groups
