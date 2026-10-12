# Quickstart: First Scheduling Slice

## Required configuration

- PostgreSQL connection for domain tables, idempotency records, and graph checkpoints.
- Durable queue connection for import and scheduling jobs.
- An authentication provider that supplies tenant scope or authorized operations scope.
- `ANTHROPIC_API_KEY` only when a later Anthropic-backed node is enabled. Do not add it to a CSV,
  source file, log, or client response.

## Run the first slice

1. Start PostgreSQL and the job worker.
2. Apply migrations that create tenant-scoped WOs, workflow runs, and the handyman's non-overlap
   constraint.
3. Create the single active handyman record.
4. Submit a CSV with the required six headers through `POST /v1/import-jobs`.
5. Poll the import job until every row has an outcome.
6. Queue scheduling for an eligible WO and poll its workflow result.

## Verify the invariants

1. Import two WOs from different tenants and confirm each tenant can read only its own WO.
2. Submit equal requested times for two WOs. Confirm only one can become scheduled and the other
   becomes `needs_review`.
3. Submit WOs with every priority. Confirm feasible work is considered in critical, high, normal,
   then low order; ties use submission order.
4. Resubmit the same CSV row or scheduling request with the same idempotency key. Confirm no
   duplicate WO or appointment exists.
5. Stop a worker during a run and restart it. Confirm the graph resumes or records a recoverable
   outcome without violating the capacity rule.
