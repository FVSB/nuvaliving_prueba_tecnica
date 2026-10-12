# gpt-6-luna implementation handoff

**Requested model**: `gpt-6-luna` for implementation, as explicitly requested by the user.  
**Current gate**: `tasks.md` is generated and the spec/plan/tasks consistency review is complete; no feature policy blockers remain.  
**Next workflow**: Read `.agents/skills/speckit-implement/SKILL.md` and process the unchecked tasks in dependency order using `gpt-6-luna`. The user requested planning first, then this model for development; that authorization persists for the concrete feature scope in the authoritative artifacts. Do not insert a redundant generic approval prompt.  
**Status**: Implementation and automated application tests have not been completed by this planning handoff.

## Authoritative artifacts

- [spec.md](spec.md) and [Decision 005](../../docs/decisions/005-visit-negotiation.md) define business behavior.
- [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/negotiation.md](contracts/negotiation.md), and [quickstart.md](quickstart.md) define the proposed design.
- `docs/BUSINESS_RULES.md` is the binding functional source, synchronized for the approved policies.
- `docs/TECHNICAL_ARCHITECTURE.md` and the project constitution remain authoritative for architecture and workflow.

## Handoff invariants

1. Start by processing `tasks.md` in dependency order; keep changes within spec/plan/tasks and the documented architecture.
2. Keep exactly two terminal values using `TerminalStatus(StrEnum)`: `SCHEDULED="scheduled"` and `REQUIRES_REVIEW="requires_review"`. `ReviewReason` is separate explanation data.
3. Ask tenant availability first; split explicit windows into two-hour candidates; pre-filter shared occupancy/priority before asking the handyman. Transfer holds only after tenant selects/authorizes a candidate.
4. Availability is not consent. Get explicit yes/no for the immutable proposal from both participants. Ambiguous interpretation is null plus clarification-required.
5. Use one global schedule authority for every read/write. Retain graph state across queued inbound messages; nodes do not read stdin or block waiting for future human input.
6. Atomic schedule commit also writes the scheduled domain status and sets finalization pending. Confirm both participants sequentially before emitting the scheduled frame. Commit and review closure are mutually exclusive. Exact `<NO RESPONSE>` closes only an unfinished order immediately; do not retry it or let delayed input change a terminal outcome.
7. Preserve the two-line CLI terminal frames, provide deterministic evidence-based single-line review reasons, and never fabricate unknown availability or dates.
8. Reuse the existing injected Anthropic client and trace facilities. Keep network/model/provider errors distinct from participant silence. Report checks only when actually run.

## Baseline facts from CodeGraph

The startup coordinator currently discards returned graph state, inbound messages use a separate echo handler, the graph ends after language recognition and fixed-Spanish initialization, stdout has a message-block writer but no terminal writer, and JSONL appends are serialized. Plan implementation against those facts rather than treating proposed nodes/ports as existing code.
