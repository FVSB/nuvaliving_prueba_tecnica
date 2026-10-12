# Decision 002: Startup local timezone

**Status**: Approved, 2026-10-12

`LOCAL_TIMEZONE` is an IANA timezone read once through startup settings. It defaults to
`Europe/Madrid`, is injected into CSV parsing, and normalizes every offset-aware `reported_at`
without changing its instant. The user approved this configuration exception for the initial CSV
bootstrap. Changing it requires a new process run; it never mutates active work-order state.
