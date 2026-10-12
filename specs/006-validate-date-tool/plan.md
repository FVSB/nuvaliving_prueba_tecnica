# Implementation Plan: Deterministic Date, Role, and Input Validation Fixes

**Branch**: `006-validate-date-tool` (logical; work on `005-vague-slot-suggestion`) | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)

## Summary

Add a pure `domain/date_validation.py` tool applied by code to every extracted interval, enforce
visit hours 09-19 Europe/Madrid and a configurable horizon, route clarification answers by role,
add cancel/correct decisions, validate inbound input (known WO, non-empty, max length) before any
LLM, and reorder checks so deterministic validation precedes the LLM stage. Executed in waves by
packages A, B1, C (wave 1, parallel), B2 (wave 2), and V (verification).

## Technical Context

**Language/Version**: Python 3.12 (`uv`) | **Dependencies**: no new ones | **Storage**: in-memory
agenda + JSONL traces | **Testing**: `pytest` with deterministic fakes and `--now` clock |
**Constraints**: no global state or clock reads in domain code; settings already in `config.py`
(`visit_horizon_days`, `max_message_length`, slot hours).

## Constitution Check

- [x] I. Normative sources separate: `BUSINESS_RULES.md` updated with only the essential new rules;
  this spec and plan carry mechanics and do not redefine business policy.
- [x] II. Explicit developer approval: user decided visit hours 09-19; each package is delegated by
  the user. Open decision OD-001 (horizon vs slot table) is left to the user.
- [x] III. Deterministic business boundaries: all date/hour/horizon/input rules are code; the LLM
  supplies evidence only. FR-008 amends spec 005 FR-005 so the LLM validator runs after deterministic
  checks and is never authority.
- [x] IV. Explicit, typed, injectable runtime: `DateCheck`/`DateErrorCode` are typed, the clock and
  settings are injected, no global state.
- [x] V. Verifiable incremental delivery: small packages with deterministic tests, wave order, and a
  verification package V.

## Project Structure

```text
src/maintenance_agent/
  domain/date_validation.py        # A (new)
  domain/decisions.py              # B1
  application/conversation.py      # A (AvailabilityInterpretation.invalid_reason)
  application/workflow.py          # B1 (handle/_ask/_clarify/NO RESPONSE/decisions), B2 (slots, records)
  application/coordinator.py       # C
  application/messages.py          # C
  application/rejections.py        # C (optional)
  infrastructure/cli_transport.py  # C
  infrastructure/anthropic_*.py    # A (thinking disabled, prompts)
  infrastructure/in_memory_schedule.py, domain/scheduling.py   # B2
tests/  unit + integration per package
```

## Wave Order

1. Wave 1 (parallel, disjoint files): A, B1, C, E.
2. Wave 2: B2 (depends on A's `validate_interval` and B1's `workflow.py` edits).
3. Wave 3: V (full suite, live smoke with `--now 2026-10-12T12:00:00+02:00`, E-final doc fill-in).
Ruff E501 warnings are handled separately by the orchestrator with user permission.

## Risks

- OD-001 resolved: horizon stays 7, table capped to it (see spec Known Risks and Limitations).
- `workflow.py` is shared by B1 and B2: strict function-level ownership and wave order.
- Error 16 (double offer before hold) is conforming behavior per BUSINESS_RULES; documented as a known risk.

## Complexity Tracking

None; no new services, dependencies, or settings beyond those already present.
