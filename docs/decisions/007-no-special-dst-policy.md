# Decision 007: No special DST policy

**Date**: 2026-10-12
**Status**: Approved by user
**Supersedes**: the DST clause of Decision 005, item 7

## Context

Decision 005 deferred any two-hour visit crossing a daylight-saving transition to human review and
left DST semantics as an open policy. The code never implemented that deferral.

## Decision

No special DST policy. Offsets (`+01:00` / `+02:00`) come from the IANA timezone database through
`ZoneInfo(LOCAL_TIMEZONE)`, instants are compared in UTC, and visits run only 09:00-19:00
`Europe/Madrid`, so they never overlap the overnight transition. A DST-window environment
variable and a custom tzinfo were considered and rejected: they duplicate what `ZoneInfo` already
does and would need yearly maintenance.

## Consequences

- `BUSINESS_RULES.md` drops the DST deferral and the "DST semantics" pending policy.
- `docs/configuration.md` and `docs/IMPLEMENTATION.md` are synchronized.
- Older specs and Decision 005 keep their historical wording; this decision prevails.
