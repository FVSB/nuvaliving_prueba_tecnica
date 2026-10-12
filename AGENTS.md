<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan at
`specs/001-async-work-order-scheduling/plan.md`.
<!-- SPECKIT END -->

<!-- GENTLE-AI / ENGRAM START -->
## Gentle-AI, Engram, and Specify coexistence

Engram is the persistent-memory layer for this workspace. It may retain and
retrieve project decisions, discoveries, and session context, but it does not
replace the project's SDD source of truth.

Specify/SpecKit remains authoritative for specification, planning, task
generation, and implementation: use the existing `.specify/` workflows and
the current `specs/` artifacts. Do not create or migrate work into Gentle-AI
ODD planning artifacts, and do not overwrite `.specify/`, `specs/`, or this
file when syncing Gentle-AI.
<!-- GENTLE-AI / ENGRAM END -->

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
