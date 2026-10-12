# Research: Negotiate Visit Slots

**Date**: 2026-10-12  
**Status**: Complete from approved policy and repository evidence; no external research claims

## Decisions

### Candidate source and granularity

- **Decision**: Ask the tenant for all explicit availability intervals first. Merge overlapping/adjacent windows into their union, then split the union into consecutive two-hour candidates and ignore a residual shorter than two hours. The handyman may counter-propose a different two-hour interval only if it is fully contained in the tenant's original explicit union; this is availability evidence, not consent. Apply agenda pre-filtering to counterproposals and ask tenant to confirm the exact slot. All different-start intervals are checked for overlap by the shared agenda.
- **Rationale**: There is no external calendar or approved fixed grid. The participant-provided interval is the time boundary; slicing it into initial candidates must not prevent a contained counterproposal such as 10:00–12:00 within a tenant's 09:00–13:00 availability.
- **Alternatives considered**: A prebuilt calendar grid (would invent availability); asking handyman globally before tenant (rejected by approved tenant-first flow).

### Priority transfer

- **Decision**: A tenant-requested candidate may atomically transfer every overlapping lower-urgency tentative hold if no equal/higher hold or confirmed appointment overlaps. A confirmed appointment is immutable. A denied request asks for another candidate or all availability.
- **Rationale**: One explicit deterministic agenda rule avoids simultaneous contenders and priority races.
- **Alternatives considered**: Coexisting holds (cannot represent one shared agenda deterministically); displacing confirmed visits (breaks agreement and terminality).

### Consent and interpretation

- **Decision**: Availability is not consent. Tenant and handyman each answer a yes/no question for the current immutable proposal ID/version. A typed interpreter returns `decision: yes | no | null` and `clarification_required: bool`; ambiguous output is never coerced. Evidence is bound to the unique outstanding role question and current state/proposal versions.
- **Rationale**: Existing CLI input has no correlation ID, so only one outstanding question per role/order can bind an answer. If a delayed answer cannot be distinguished, ask for the full slot again; do not claim perfect stale-message detection.
- **Alternatives considered**: Treating availability as acceptance (forbidden); guessing yes/no from ambiguous input (unsafe); adding protocol fields (outside scope).

### Empty candidate set and silence

- **Decision**: Pre-filter every tenant candidate by known shared occupancy before asking the handyman. If all candidates are blocked, ask for alternatives/all availability. Once the tenant confirms that set is exhausted and known agenda blockers leave no eligible candidate or contained handyman counterproposal, ask about human scheduling; this is `no_eligible_slot`, even if handyman availability is unknown. Separately, `no_common_availability` requires known complete tenant and handyman evidence, including contained counterproposals, that has no common eligible interval. Partial/unknown handyman evidence alone triggers a request for missing information. Yes to human scheduling ends in `requires_review`; no restarts tenant availability collection; ambiguity is clarified. Exact `<NO RESPONSE>` from either role immediately ends an unfinished order in `requires_review`; no retry. Provider/transport error is not participant silence.
- **Rationale**: Known agenda occupancy can prove no eligible tenant-requested slot without evidence from the handyman, while a claim of no common availability depends on complete evidence from both participants.
- **Alternatives considered**: Retrying silence (not approved); treating an LLM/provider error as human absence (semantically false).

### Concurrency, state, and commit

- **Decision**: Preserve per-work-order graph state across inbound invocations, serialize each order's event queue, and use one schedule authority lock for every shared read/write. Return detached immutable snapshots. Revalidate immediately before each mutation; never hold the lock across model, human, or transport waits. Commit is atomic and immutable; send both confirmations before `scheduled`.
- **Rationale**: Repository baseline calls the graph at startup but discards returned state, then routes inbound messages to an injected echo handler. The negotiation implementation must replace that lifecycle behavior. Existing stdout writer serializes complete message blocks, and trace writer already serializes JSONL appends.
- **Alternatives considered**: Per-order calendars (violate one shared handyman agenda); LLM authority over schedule (violates deterministic boundary); holding a lock during waits (blocks unrelated orders and risks deadlock).

### No-common-time follow-up

- **Decision**: Follow the distinction above: tenant-window exhaustion plus known agenda blockers can establish no eligible slot; a no-common claim requires complete known tenant and handyman evidence and considers contained handyman counterproposals. Ask tenant whether they want human scheduling. A no requests new tenant availability; a yes uses the existing `requires_review` terminal. Unknown/partial state asks the missing participant for information.
- **Rationale**: Keeps exactly two terminal outcomes and avoids treating unknown evidence or a graph wait as a business result.
- **Alternatives considered**: A third `no_availability` status (not allowed); calling no common time while handyman availability is unknown (unsupported).

### Language, time, and observability

- **Decision**: Store tenant language per `(work_order_id, role)`, support the recognized catalogue including Spanish and English, and keep handyman Spanish. Normalize times to UTC; display in approved `LOCAL_TIMEZONE`, default `Europe/Madrid`. Reuse the existing startup configuration and JSONL trace machinery; do not add settings.
- **Rationale**: CSV has no stable tenant identity or language field; the approved scope expands language support. Existing architecture defines the timezone and traces.
- **Alternatives considered**: Cross-order identity inference or new CSV fields (out of scope); a new timezone knob (unneeded); traces containing prompts/secrets (forbidden).

## Repository Evidence

- `BUSINESS_RULES.md` defines CSV/CLI framing, two terminal values, exact no-response token, urgency order, two-hour visits, and timezone baseline. Decision 005 records the specifically approved policy changes and implementation boundary.
- `TECHNICAL_ARCHITECTURE.md` defines injected dependencies, per-work-order sequential state, shared agenda locking, no lock across waits, startup-only composition, and JSONL observability.
- The 003 plan establishes the existing LangGraph and language recognition integration path.
- CodeGraph inspection supplied to this planning task found that `AsyncCoordinator._start` invokes the current graph then discards returned state; inbound `_consume` invokes a separate `inbound_node`. The current graph is `START -> recognize_language -> initialize_coordination -> END`; initialization is fixed Spanish. `AsyncStdoutWriter` serializes message blocks, and `TraceWriter` serializes event writes. These are baseline facts, not claims about this feature's implementation.

## Resolved Policy Questions

All prior policy blockers are resolved by the user-provided decisions recorded above and in [Decision 005](../../docs/decisions/005-visit-negotiation.md). No unresolved clarification remains in the feature plan.
