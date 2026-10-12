<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan at
`specs/005-vague-slot-suggestion/plan.md`.
<!-- SPECKIT END -->

## Ruff rule

Before investing time in manual Ruff fixes, ALWAYS ask the user first
whether to spend time on Ruff or not. Never proceed with manual (non
auto-fixable) Ruff fixes without explicit user approval. `poe auto-fix`
(`uv run poe auto-fix`) may be run freely — it only applies safe
automatic fixes.

<!-- GENTLE-AI  START -->
## Gentle-AI, and Specify coexistence

Specify/SpecKit remains authoritative for specification, planning, task
generation, and implementation: use the existing `.specify/` workflows and
the current `specs/` artifacts. Do not create or migrate work into Gentle-AI
ODD planning artifacts, and do not overwrite `.specify/`, `specs/`, or this
file when syncing Gentle-AI.
<!-- GENTLE-AI  END -->

<!-- CODEGRAPH START -->
## CodeGraph

This repository has a CodeGraph MCP server: use it first for structural code
questions. It is a tree-sitter knowledge graph, so it answers symbol,
call-graph, impact, and flow questions without reconstructing them with grep.

Use CodeGraph for:

| Need | Tool |
|---|---|
| Find where a symbol is defined or its signature | `codegraph_search` or `codegraph_node` |
| Find callers or callees | `codegraph_callers` or `codegraph_callees` |
| Trace an end-to-end flow, including framework callbacks | `codegraph_trace` |
| Assess the impact of changing a symbol | `codegraph_impact` |
| Obtain focused context or several related symbol bodies | `codegraph_context` or `codegraph_explore` |
| List indexed files or check index health | `codegraph_files` or `codegraph_status` |

Use `rg` and targeted file reads for literal text: exact strings, comments,
logs, configuration values, or files reported as pending by CodeGraph. Do not
start a symbol lookup with grep or re-verify fresh CodeGraph results with grep.

When CodeGraph reports files pending index sync, read only those named files
for current contents; the remaining graph data is authoritative. If the graph
is uninitialized, ask before running `codegraph init -i`.
<!-- CODEGRAPH END -->

## Cost-efficient documentation work

For work limited to reading, reviewing, creating, or editing Markdown documentation — including
`*.md` skills, specifications, plans, checklists, decisions, and agent instructions — delegate to
the lowest-cost capable Codex model available. Prefer `gpt-6-luna` when it is available; use a
more capable model only when the requested documentation work requires reasoning or technical
judgment that the lower-cost model cannot reliably provide. Do not apply this preference to code,
tests, security-sensitive changes, or tasks that require repository-wide architectural analysis.

## Reproducible development installations

Every approved installation MUST be recorded in the same change:
- Application Python dependencies: `uv add <package>`; dev-only Python dependencies:
  `uv add --dev <package>`. Retain and version `pyproject.toml` and `uv.lock`.
- Node development CLIs: `.devcontainer/package.json` with explicit versions and its
  `package-lock.json`; update the lock with `npm install --package-lock-only --prefix .devcontainer`.
- Go CLIs: `.devcontainer/go-tools.txt`, one versioned module per line.
- Python environment tools: `.devcontainer/requirements-tools.txt`, with pinned versions.
- OS packages: `.devcontainer/apt-packages.txt` (versions follow the base Debian repositories).
- Container features/base: `.devcontainer/devcontainer.json`, `Dockerfile`, and feature lockfile.

Do not treat a manual installation in a running container as delivery. Keep the installation
recipe and lockfiles synchronized, document purpose and verification in `docs/development.md`,
and verify a clean rebuild when Docker is available. Preserve workspace skills, agent configs,
and indexes; never migrate secrets, live SQLite databases, or authentication files into images.
