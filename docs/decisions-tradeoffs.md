# Business and technical decisions, and possible extensions

Summary of assumptions and trade-offs in the [README](../README.md#decisions). This document has the details.

## Business decisions

1. **A simplified planning horizon.** This take-home test considers dates up to today plus seven days, inclusive, to keep planning simple. In a real deployment, the planning window would be organized around complete calendar weeks. The agent states its current limit instead of offering later dates.

2. **Reject invalid intervals without trimming them.** An interval outside the permitted hours or the horizon is rejected as submitted. Trimming it automatically would change what the participant actually said they could accept.

3. **Allow consecutive visits without a buffer.** We assume the handyman can finish one visit and start another immediately: 14:00–16:00 and 16:00–18:00 are compatible. Travel and preparation time are not part of this scheduling model.

4. **Ask the tenant first.** Establishing the household's availability before consulting the handyman avoids negotiating visits the tenant cannot attend.

5. **Request all available intervals.** Collecting the full set gives the agent alternatives if a slot is occupied or unsuitable for the handyman, reducing repeated questions.

6. **Merge overlapping and adjacent availability.** This removes duplicates and keeps usable continuous windows. For example, 10:00–11:00 and 11:00–12:00 together allow a full two-hour visit, although neither interval does so alone.

7. **Generate two-hour candidates from the tenant's stated start.** Each candidate must fit the visit duration required by the assignment. Availability from 10:00 to 15:00 produces 10:00–12:00 and 12:00–14:00; the final hour cannot fit a visit. Starting from the tenant's own interval avoids inventing a separate booking grid.

8. **Check conflicts before consulting the handyman.** Candidates blocked by a confirmed appointment or by a tentative reservation of equal or higher urgency are discarded, avoiding questions about slots that cannot be assigned.

9. **Give urgency priority during an unfinished negotiation.** If a Low order holds a tentative reservation and a Critical order needs the same time, the Critical order can take that reservation after its tenant explicitly accepts the proposed visit. The transfer is atomic and only succeeds if no reservation of equal or higher urgency and no confirmed appointment blocks it. This enforces the assignment's urgency rule while protecting visits already agreed with both parties.

10. **Allow simultaneous offers before reservation.** Two negotiations may offer the same currently free slot. Competition is resolved when the reservation is acquired. A lower-urgency order can keep it if it becomes a confirmed appointment first; confirmed visits are not displaced.

11. **Notify the tenant whose reservation was displaced.** The affected order continues with an explanation in the tenant's language and an eligible alternative, or a request for new availability. Its proposed time is never silently reassigned.

12. **Offer human coordination when options are exhausted.** Once there is complete evidence that no eligible common visit exists, or known agenda conflicts exhaust the tenant's full request, the agent asks whether the tenant wants human scheduling. If accepted, the result is `requires_review`; if declined, the agent asks for new availability.

13. **Explain review outcomes from recorded evidence.** Reasons use `no_response`, `no_common_availability`, or `no_eligible_slot`, plus the known facts. Unknown availability is explicitly described as unknown, so whoever takes over understands what prevented scheduling.

## Technical decisions

1. **Interpret explicit confirmations with code.** Yes/no decisions are handled deterministically from a closed list of Spanish and English variants, with or without accents (`sí`/`si`/`yes`, `no`/`rechazo`/`reject`, etc.). Courtesy words are ignored. Any other reply to a yes/no question is asked again, rather than being turned into acceptance, rejection, or new availability by the model. See [research.md](../specs/004-negotiate-visit-slots/research.md), "Yes/no reply variants and re-ask".

2. **Separate provider failures from participant silence.** An Anthropic error is a technical incident recorded in the runtime trace. It does not mean a tenant or handyman failed to answer, and it is never converted into a human timeout.

3. **Keep structured traces for each execution.** Messages, state changes, decisions, and results are correlated by run and work order. Separate manifest, event, and runtime files make the coordination reconstructable, while stdout and stderr stay reserved for the communication protocol. See [traces and tests](traces-and-tests.md).

4. **Read configuration and assemble dependencies once at startup.** Every conversation in a run uses the same settings. Changes require a restart; dependencies are injected instead of being recreated or reconfigured inside graph nodes.

5. **Retry waits use the real clock (disabled by default).** Retries after `<NO RESPONSE>` use the real UTC clock. The assignment asks not to use real-time waiting or wall-clock timeouts. For that reason the feature is disabled by default (`no_response_retries_enabled=false`), and closing immediately as `requires_review` is the deliverable behavior. If it is enabled, this decision must be reviewed before it is used in evaluation.

## Possible extensions

These are possible additions for a real deployment, subject to business policy and richer operational data.

1. **An agenda optimizer.** A scheduling manager could offer discrete booking slots and coordinate competing orders globally, prioritizing the completion of Critical and High negotiations before assigning capacity to lower-urgency work. This would reduce the current dependence on which conversation confirms first. Business rules would define how long tentative slots can be held and how to avoid postponing less urgent work indefinitely.

2. **Planning by building.** If the business assigns particular days or slots to each building, those constraints could shape the availability offered. Grouping visits by location and including travel buffers could reduce travel and improve capacity use. The current model does not account for building schedules or travel between addresses.

3. **Planning by maintenance type and difficulty.** Grouping similar reports could reduce repeated preparation and equipment changes. Difficulty could inform duration, required skills, and technician assignment, while urgency stays an explicit business priority. This would require work-order data beyond the current CSV and an extension of the fixed two-hour, single-handyman model.

4. **Materials and external dependencies.** Scheduling could account for parts, supplies, access permissions, or external contractors. A visit could be offered once its prerequisites are ready, with the reason for any delay visible to the tenant and the operations team.

5. **Visual slot selection.** A calendar interface, such as a Calendly-style or Cal.com-style booking flow, could let tenants select eligible slots directly when availability is already known. This would reduce back-and-forth in straightforward cases, while the agent handles ambiguity, exceptions, and changes. Selection would still need to respect shared agenda conflicts and the handyman's availability and acceptance.
