# Quickstart: Negotiate Visit Slots

This guide describes the planned runtime behavior for later implementation. It is not evidence that the feature currently runs.

## Conversation sequence

1. Startup recognizes tenant language and sends an incident-grounded introduction plus a request for all explicit availability intervals.
2. Overlapping/adjacent tenant intervals are merged into a UTC union, then split into full consecutive two-hour initial candidates. No external calendar or fixed grid is consulted.
3. Before asking the handyman, the shared agenda pre-filters each tenant candidate. Candidates blocked by an equal/higher tentative hold or confirmed appointment are reported to the tenant for alternatives. Free or strict-higher-priority preemptible candidates can be put to the handyman.
4. The handyman supplies explicit evidence for the remaining candidates. A handyman counterproposal at a different start is accepted only if fully contained in the tenant's original interval union; it is pre-filtered against the agenda and the tenant is asked to confirm that exact slot. Unknown or partial evidence asks for missing information.
5. A candidate with both participant availability and agenda eligibility becomes an immutable versioned proposal. The tenant and handyman answer separate explicit confirmation questions for that exact proposal.
6. A matching pair of yes decisions allows atomic schedule revalidation and commit. Both receive final confirmations before the single `scheduled` terminal frame.
7. Exact `<NO RESPONSE>` from either role on an unfinished order immediately produces `requires_review`; a delayed message during scheduled finalization cannot change it. If all tenant candidates are blocked, request alternatives/all availability first; when the tenant confirms the set is exhausted and no contained counterproposal remains, offer human scheduling even if handyman availability is unknown. Separately, known complete tenant and handyman evidence, including contained counterproposals, with no common time offers the same choice. Yes produces `requires_review`; no asks for new tenant availability.

## Key invariants to verify during implementation

- Terminal type has exactly two values: `scheduled` and `requires_review`; it is unset during graph progress or waits.
- Availability never means consent; ambiguous confirmation never means yes or no.
- The same agenda authority serializes every schedule read and write and returns immutable detached snapshots.
- No schedule lock crosses a model, participant, or transport wait.
- Committed visits cannot be displaced, even while confirmation delivery is pending.
- Tenant language is per work order; handyman language is Spanish.
- Show participant times in `LOCAL_TIMEZONE`, default `Europe/Madrid`; compare normalized UTC instants.
- Keep existing CLI framing and process-local state.

## Planned implementation checks

Later tasks must include meaningful tests for interval boundaries, candidate creation, occupancy pre-filtering, atomic multi-hold transfer, agenda races, stale/duplicate decisions, no-response exact matching, graph continuation, terminal idempotency, and protocol output. Report test, fake-provider, Docker, and real-provider results separately; do not imply provider access when only fakes were used.
