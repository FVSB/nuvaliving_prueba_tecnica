---
name: "gentle-review"
description: "Run or continue a Gentle-AI evidence review when the user explicitly requests a Gentle review or a reliability, risk, resilience, or readability review."
---

## Purpose

Use Gentle-AI's review workflow only for an explicitly requested review. It
produces evidence against a frozen candidate; it does not replace the
project's Specify/SpecKit SDD workflow or ordinary repository merge policy.

## Start a review

1. Inspect `git status --short` first.
2. If untracked files exist, obtain the canonical inventory before starting:

   ```bash
   gentle-ai review status --cwd . --contract gentle-ai.review-integration/v2 --agent codex --next-transition
   ```

3. Ask the user whether untracked files belong in the review if that choice
   would materially change the candidate. Otherwise, exclude them to avoid
   reviewing generated configuration or unrelated local files.
4. Start the requested lens, for example:

   ```bash
   gentle-ai review start --cwd . --focus reliability
   ```

Use the exact inventory digest returned by the status command whenever
`review start` requires it. Do not invent a digest or select paths that were
not present in the canonical inventory.

## While a review is active

- Use `gentle-ai review status --cwd .` to inspect authoritative state.
- Do not change files in the frozen candidate. If the worktree changes, say
  that the review must be restarted before it can be completed.
- Follow any authority-provided capture and validation transition exactly.

## Boundaries

- Specify/SpecKit remains authoritative for specification, planning, tasks,
  and implementation.
- Treat review findings as evidence for the user; do not modify code or
  repository policy solely because a review was started.
- `gentle-ai doctor` is read-only and can be used to diagnose the local
  Gentle-AI, Codex, and Engram integration.
