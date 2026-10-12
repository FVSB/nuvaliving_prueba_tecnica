# Decision 008: Docker delivery and terminal contract

**Date**: 2026-10-12
**Status**: Approved by explicit user request to implement the take-home PDF contract

## Context

The take-home evaluator requires a root Dockerfile, a locked runtime installation, protocol-only
terminal output, structured traces under `/app/traces`, and exactly one terminal result per work
order. The evaluator supplies its CSV and sends replies over stdin. Completion must prevent later
input from reopening an order or creating extra output.

## Decisions

1. The root Dockerfile installs the application from `uv.lock` with
   `uv sync --frozen --no-dev --no-editable`, and creates `/app/traces` in the image. Runtime
   credentials are supplied with `--env-file`; they are not baked into the image.
2. The coordinator marks an order complete only after its terminal frame has been written. After
   that point it ignores valid, rejected, and already-queued inputs for that order; none can produce
   another reply or terminal result. Known rejected inputs are serialized through that order's
   queue, preserving its per-order event order.
3. An `outgoing_message` trace event is written only after the complete output block has been
   flushed. It records the actual body and recipient role that were sent. A `terminal_result` trace
   event is written only after its terminal frame has been written.
4. `tests/integration/test_input_validation.py` covers duplicate and late valid/rejected inputs for
   terminal orders. `tests/acceptance/test_negotiation_cli.py` verifies that confirmation messages
   precede the terminal trace event.

## Verification and limitation

On 2026-10-12, all 357 pytest tests passed, `docker build -t agent .` succeeded, and the Docker
runtime smoke test exited successfully with empty stderr. The container used the evaluator's
read-only CSV and traces mounts with `.env`; Anthropic recognized the English and Spanish work-order
descriptions, both inputs timed out, and each order emitted exactly one `requires_review` result.
The captured input, output, and JSONL traces are in `examples/docker-run/`. This Docker smoke test
verifies startup, protocol framing, and timeout handling; it does not verify a scheduled negotiation
inside Docker. A separate local CLI run with Anthropic scheduled one order and sent the other to
review; see the live run linked from the README.
