# Decision 004: Tenant-language inference from work-order descriptions

**Status**: Approved, 2026-10-12

The user approved a first workflow step that infers the language of each work-order description
and records an ISO 639-1 language result before later coordination actions. The feature uses a
reusable catalogue of common language codes and a single explicit undetermined value whenever the
description does not provide reliable evidence for one language. It must never guess under
uncertainty.

This decision satisfies the explicit-approval requirement in `BUSINESS_RULES.md` for
tenant-language inference. It does not change the current binding communication policy: tenants
are addressed in Spanish or English only. Recognition of another common language is recorded for
future policy-approved handling, not used to send a message in that language. All new identifiers,
variables, prompts, and model instructions for this workflow use English.
