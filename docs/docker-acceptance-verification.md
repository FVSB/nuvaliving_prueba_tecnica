# Docker verification: acceptance and refusal that restate a date

This note records a targeted end-to-end check of one negotiation rule in the delivered Docker image.

## Rule under test

A tenant reply that restates a proposed visit should be read as follows:

- **Restates the exact proposed date and time** (for example "Yes, I accept 2026-10-14 10:00-12:00."
  when the proposal is 2026-10-14 10:00-12:00) counts as an explicit yes.
- **Names a different time** (for example "Sí, acepto 2026-10-15 15:00-17:00.") does not count as
  acceptance. It is treated as new availability.
- **A leading refusal with a date** (for example "no, I cannot do the 14th") counts as a refusal and
  moves the order to alternatives. It must not loop on the yes-or-no question.

Automated tests cover these rules in `tests/unit/test_decisions.py` and
`tests/integration/test_handyman_slot_acceptance.py`.

## Setup

- Image: `agent`, built from the current working tree with `docker build -t agent .`.
- Input: `examples/work_orders.csv`, mounted read-only, with `--env-file .env` and a trace directory.
- Model: `claude-haiku-5-5`, Europe/Madrid timezone.
- Each run was driven by a script that writes protocol lines to stdin and records every stdout block
  with a timestamp.

## Results

| Case | Input (tenant unless noted) | Observed | Verdict |
|---|---|---|---|
| T-A | Availability 2026-10-14 10:00-12:00. Handyman "sí". Tenant "Yes, I accept 2026-10-14 10:00-12:00." Handyman "sí, acepto". | `RESULT:scheduled`, `SCHEDULED_FOR:2026-10-14T10:00:00+02:00`. The tenant was not asked yes-or-no again. Two `participant_decision_recorded` events, both `yes`. Stderr empty. | PASS |
| T-B | Availability 2026-10-15 09:00-11:00. Handyman "sí". Tenant "Sí, acepto 2026-10-15 15:00-17:00.". | No `RESULT`. The tenant's reply was recorded as changed availability and the agent asked for confirmation. Zero decision events. The run was closed after 180 s without a result. Stderr empty. | PASS |
| T-C | Availability 2026-10-14 10:00-12:00. Handyman "sí". Tenant "no, I cannot do the 14th". | The refusal was read as a refusal: `workflow_transition` to `tenant_alternatives` and `hold_released` with reason `proposal_rejected`. The agent asked for another interval. No `RESULT`, no repeated yes-or-no loop. Stderr empty. | PASS |
| T-C2 (control) | Same as T-C, but tenant "maybe, not sure". | Not read as yes or no: the transition stayed at `tenant_confirmation` and the agent asked for a clear yes or no. No scheduling. Stderr empty. | PASS |

Each case ran in its own container with a single order or a pair of orders. Stderr was empty and the
exit code was 0 in every run. No Python traceback appeared in any run.

## Limits

- T-B closed on the 180 s driver timeout, not on a terminal result. This shows the fix does not
  accept a different time; it does not show what the agent does next in a longer conversation.
- Only one scenario per rule was run.
- This build emits no `participant_decision_recorded` event for a refusal or an unsure reply, so the
  outcome of T-C and T-C2 is read from the workflow transition and the hold release, not from a
  decision value.
- The first T-C attempt sent the refusal without the `WO-001|tenant ` prefix. The agent never
  dispatched it, so it is not counted; the driver was fixed and the case re-run.
