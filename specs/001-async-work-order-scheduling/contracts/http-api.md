# HTTP Contract: Async Work-Order Scheduling

All endpoints require an authenticated operations identity. Responses and requests are scoped to
the authorized tenant unless the caller has explicitly documented cross-tenant operations access.

## `POST /v1/import-jobs`

Accepts a CSV upload and returns `202 Accepted` with an import-job identifier.

Required CSV headers: `tenant_id`, `work_order_id`, `priority`, `requested_start`,
`timezone`, `contact_destination`.

Response:

```json
{
  "import_job_id": "imp_123",
  "status": "queued"
}
```

## `GET /v1/import-jobs/{import_job_id}`

Returns job status, accepted/rejected counters, and row-level error summaries appropriate to the
caller's authorization scope.

## `GET /v1/work-orders/{work_order_id}`

Returns the tenant-scoped WO, its priority, requested service window, current outcome, and
user-safe reason. Returns `404` when the WO is outside the caller's tenant scope.

## `POST /v1/work-orders/{work_order_id}/schedule`

Queues idempotent scheduling for an eligible WO and returns `202 Accepted` with a workflow run
identifier. Accepts an `Idempotency-Key` header. The eventual result is `scheduled`,
`needs_review`, or `rejected`; it never returns a conflicting confirmed appointment.

## Error Contract

Validation failures use `422` with a stable error code. Unauthorized actions use `403`. Missing
or out-of-scope resources use `404`. A duplicate request with the same idempotency key returns
the prior job or workflow reference rather than starting duplicate work.
