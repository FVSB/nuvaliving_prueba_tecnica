# Decision 003: Shared, reproducible development container

Approved by the user to preserve project agents/skills/index files and automatically reinstall
recorded tools on future container creations. Mount the entire repository at its existing absolute
path so host-specific workspace config remains usable. Mount the example CSV read-only at the
binding runtime path and host traces at /app/traces. Use a separate container Python environment.

Record installs in ecosystem-specific manifests and locks; do not copy credentials into the image
or silently import live SQLite stores. Engram uses the shared project store; stop host servers before
starting container servers. Docker runtime validation remains pending until the daemon is running.
