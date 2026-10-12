# Docker validation: urgency preemption and renegotiation

End-to-end validation of the agent **as an evaluator would run it** (`docker run -i`, CSV mounted
read-only, protocol on stdin/stdout, real Anthropic API) over a CSV of 8 work orders with mixed
urgencies and languages. The central case is a lower-urgency order that is negotiating when a
higher-urgency order takes its tentative slot, and how the agent tells the displaced tenant and
renegotiates.

Everything here is reproducible with one command and produces machine-readable metrics.

## Contents

| Path | Purpose |
|---|---|
| `work_orders.csv` | The 8 work orders under test. |
| `run.py` | Builds the image (optional), starts the container, plays tenant and handyman of every order with rule-based personas, then calls `metrics.py`. |
| `metrics.py` | Computes metrics and invariant checks from a run folder (can be re-run on any past run). |
| `results/run-1/` | Reference run: `output.txt` (stdout protocol), `inputs.jsonl` (every line sent), `driver.json`, `metrics.json`, `METRICS.md`, `traces/` (JSONL events and runtime logs), `stderr.txt`. |

A hand-driven run of the same scenario, with the full conversation read by a person, is kept in
[`examples/priority-renegotiation-run/`](../../examples/priority-renegotiation-run/).

## How to reproduce

Prerequisites: Docker, Python 3.10+ on the host (standard library only), and `.env` at the
repository root with `ANTHROPIC_API_KEY` (see `.env.example`).

```bash
python3 validation/priority-renegotiation/run.py                      # build + run + metrics
python3 validation/priority-renegotiation/run.py --no-build           # reuse the `agent` image
python3 validation/priority-renegotiation/run.py --out /tmp/val-2     # choose the output folder
python3 validation/priority-renegotiation/metrics.py <run-folder>     # recompute metrics only
```

Options: `--timeout` (whole-run limit, default 1800 s), `--gate-timeout` (see *Held replies*),
`--image`. Exit code is non-zero if a work order did not finish or a check failed. A run takes
about 3 minutes and roughly 70 model-backed messages.

The repository's own `work_orders.csv` is never touched: the scenario CSV is copied into the
output folder and mounted from there.

## Scenario

All dates are relative to the day of the run (`D+1`, `D+2`, `D+3`), so the scenario stays inside
the 7-day planning horizon whenever it is run. Handyman messages are always Spanish; the tenant
language is the one the agent infers from the order description.

| WO | Urgency | Lang | Role in the scenario |
|---|---|---|---|
| WO-001 gas leak | Critical | EN | Wants `D+1 10:00-12:00`, the slot WO-003 holds tentatively. |
| WO-007 short circuit | Critical | ES | Wants `D+1 12:00-14:00`, the slot WO-004 holds tentatively. |
| WO-002 water leak | High | ES | Vague first reply ("pasado mañana por la mañana"), then an explicit slot from the suggestion table. |
| WO-005 no heating | High | EN | Tenant never answers (`<NO RESPONSE>`). |
| WO-004 broken door | Medium | ES | Holds `D+1 12:00-14:00`, is displaced, renegotiates; the handyman rejects one offer and supplies new windows. |
| WO-008 broken window | Medium | EN | Handyman receives two options and picks one. |
| WO-003 dripping tap | Low | EN | Holds `D+1 10:00-12:00`, is displaced, renegotiates with a mix of blocked and free intervals. |
| WO-006 light bulb | Low | ES | First asks for a slot already confirmed for WO-001, then picks from the suggestion table. |

### Personas and sequencing

`run.py` reads every outgoing frame and answers it according to what it says, not to a fixed
order of lines:

- asks for availability, or shows a table of free slots, or announces a displacement
  → the next availability statement of that participant (`stages` in the persona);
- asks "is the changed availability correct?" → "yes" / "sí";
- proposes a single exact visit → "yes" / "sí" (handyman: only if the slot lies inside its
  `windows`, and once declines slots in `rejects`);
- offers several options → picks the first acceptable one;
- final confirmation or "wait for the other party" notices → no reply.

Replies are bare "yes"/"sí" on purpose: in earlier hand-driven runs a bare "Acepto" or
"I accept" was treated as ambiguous and re-asked.

**Held replies (gates).** To force the preemption, three replies are held until the traces show
the required state:

| Held reply | Released when |
|---|---|
| First availability of WO-001 and WO-007 | WO-003 and WO-004 tenants have accepted a proposal (tentative holds exist). |
| Handyman confirmation of WO-003 and WO-004 (first time) | Both holds were displaced (`hold_transferred`). |
| First availability of WO-006 | WO-001 has a terminal result (its slot is confirmed). |

A held reply is released anyway after `--gate-timeout` seconds so a missing event cannot hang the
run; this would be visible in the transcript and the missing preemption would fail the checks.

## What is measured

`metrics.py` reads `traces/runs/<id>/events.jsonl`, `output.txt`, `stderr.txt` and the CSV.

**Per work order:** urgency, inferred language, result and scheduled time, seconds from process
start to terminal result, messages sent to tenant and to handyman, inbound messages dispatched,
availability revisions, holds released, times displaced, handyman declines, suggestion tables shown.

**Run summary:** scheduled vs `requires_review`, number of preemptions (`hold_transferred`),
displaced work orders, outgoing and inbound message totals, wall-clock seconds.

**Invariant checks** (all must pass):

1. Every work order ends with exactly one terminal result in the traces.
2. stdout carries exactly one `RESULT` frame per work order.
3. stderr is empty (the console is reserved for the protocol).
4. No two scheduled two-hour visits overlap.
5. Scheduled visits lie inside 09:00-19:00.
6. At least one higher-urgency order displaced a tentative hold.
7. Every displacement goes from a strictly higher to a strictly lower urgency.
8. Each displaced tenant received a displacement notice after the transfer.
9. Displaced orders end `scheduled` in a different, non-overlapping slot.
10. A silent tenant (`<NO RESPONSE>`) ends `requires_review` with a "No response" reason (immediately by default; with retries enabled, after the reminders, see `specs/004-negotiate-visit-slots/spec.md`).

## Results (reference run, `results/run-1`)

Run on 2026-10-12 (Europe/Madrid), model `claude-haiku-5-5` for language and conversation,
image built from the working tree. Driver: converged in 172 s, 53 lines sent.
**10 of 10 checks passed.**

| Metric | Value |
|---|---|
| Work orders | 8 (7 `scheduled`, 1 `requires_review`) |
| Preemptions | 2 (WO-001 over WO-003, WO-007 over WO-004) |
| Holds released after availability change | 2 |
| Suggestion tables shown | 4 |
| Outgoing / inbound messages | 66 / 53 |
| Wall clock | 161.6 s |

| WO | Urgency | Lang | Result | To terminal (s) | Msgs tenant | Msgs handyman | Revisions | Displaced |
|---|---|---|---|---|---|---|---|---|
| WO-001 | Critical | en | scheduled `D+1 10:00` | 49.2 | 3 | 3 | 2 | 0 |
| WO-007 | Critical | es | scheduled `D+1 12:00` | 85.7 | 3 | 3 | 2 | 0 |
| WO-002 | High | es | scheduled `D+3 09:00` | 39.3 | 4 | 3 | 2 | 0 |
| WO-005 | High | en | requires_review (no response) | 5.1 | 1 | 0 | 0 | 0 |
| WO-004 | Medium | es | scheduled `D+3 11:00` | 161.6 | 9 | 8 | 8 | 1 |
| WO-008 | Medium | en | scheduled `D+3 14:00` | 26.1 | 3 | 3 | 2 | 0 |
| WO-003 | Low | en | scheduled `D+2 16:00` | 123.5 | 8 | 8 | 9 | 1 |
| WO-006 | Low | es | scheduled `D+2 09:00` | 88.4 | 4 | 3 | 2 | 0 |

### What the traces show

- **Preemption.** WO-003 and WO-004 each accepted a proposal and held their slot tentatively.
  When the Critical tenants of WO-001 and WO-007 accepted, the agent emitted
  `hold_transferred` with `displaced_work_orders` naming the lower-urgency order, then
  `workflow_transition` sent the displaced order back to `tenant_availability`.
- **Notice to the displaced tenant**, in their own language, e.g. WO-003 (EN): *"Your tentative
  visit has been displaced by a higher-priority work order, so we are no longer able to hold that
  slot… could you please share all of your current availability?"*; WO-004 (ES): *"la visita
  provisional que tenía reservada ha sido asignada a una orden de trabajo de mayor prioridad…"*.
- **Renegotiation.** The displaced tenants offered new intervals that included the now-confirmed
  slots; the agent filtered those out, asked the handyman only about free candidates, and, when
  the new availability replaced the old one, asked for confirmation before overwriting it
  (`availability_evidence_recorded` with `disputed: true`).
- **Conflict feedback.** WO-006 asked for a confirmed slot and received "Ese horario ya no está
  disponible" plus a table of free slots, then picked from it.
- **Silent tenant.** WO-005 ended `requires_review` with the "No response from tenant" reason and
  no handyman contact. (Recorded before the 2026-10-12 retry rule, when the sentinel closed the
  order immediately without reminders.)

## Notes and limits

- **LLM variance.** Wording, turn counts and times vary between runs (the hand-driven run needed
  17 tenant messages for WO-004, the scripted one 9). The checks are written against invariants,
  not against exact text or turn counts. Compare metrics across runs, not transcripts.
- **Observed friction, not failures.** Each replaced availability triggers a confirmation round,
  and a handyman "sí" right after such a prompt can be read as confirming the change rather than
  accepting the visit. This lengthens renegotiation (WO-003 and WO-004 are the longest) but did
  not break any invariant. It is a candidate for a prompt or workflow improvement.
- **Personas are rule-based.** The driver recognises prompts with regular expressions over the
  agent's wording (English and Spanish). If the agent's phrasing changes enough, a reply may be
  skipped and the run will time out instead of passing silently. A timeout is reported as a
  failed run, not a pass.
- **Real clock.** Unlike `tests/live/`, which freezes the clock, this run uses the container's
  real time, exactly like an evaluator's run. Running it at 23:59 or just before a week boundary
  can shift which slots exist.
- **Cost.** Each run issues on the order of a hundred Anthropic calls (guard, interpretation,
  message composition). Keep it out of the unit-test suite.
- **Credentials.** `.env` is passed to the container with `--env-file` and never copied into the
  results folder.
