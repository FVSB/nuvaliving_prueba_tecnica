# Feature Specification: Async CLI Bootstrap

**Feature Branch**: `002-async-cli-bootstrap`  
**Created**: 2026-10-12  
**Status**: Draft  
**Input**: User description: "Create a separate asynchronous task with dependency injection, startup environment loading, live stdin ingestion, regex parsing, and protocol output for the specified work order and role."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Receive and Echo a Live Work-Order Message (Priority: P1)

An operator runs the coordinator and sends a valid message for a work order through standard input. The coordinator immediately receives the whole message, associates it with the stated work order and role, and emits a complete protocol message containing the received body.

**Why this priority**: It proves the runtime can interact with an unfinished work order in real time without blocking other work.

**Independent Test**: Start the program, send one valid input line, and verify one flushed, correctly addressed protocol block is received on standard output.

**Acceptance Scenarios**:

1. **Given** a running coordinator and an input line in the documented format, **When** the line arrives, **Then** its work-order identifier, role, and complete body are available to the first workflow step.
2. **Given** a valid live message, **When** the first workflow step completes, **Then** standard output contains exactly one complete outbound block addressed to the stated work order and role with the same body.
3. **Given** messages for two unfinished work orders, **When** they arrive without waiting for one another, **Then** receipt of one does not prevent the other from being received and processed.

---

### User Story 2 - Start with Validated Runtime Configuration (Priority: P2)

An operator supplies startup configuration, including an Anthropic credential when needed by future AI workflow steps. The coordinator reads configuration once at startup and makes it available through its configured dependencies without exposing the credential in protocol output.

**Why this priority**: Future workflow nodes need reliable configuration, while the initial communication slice must remain safe without an AI call.

**Independent Test**: Launch the process with and without the credential and verify the initial echo workflow starts in both cases and never prints the credential.

**Acceptance Scenarios**:

1. **Given** an optional environment file and process environment, **When** the coordinator starts, **Then** its runtime settings are established once before messages are handled.
2. **Given** an Anthropic credential, **When** a message is echoed, **Then** neither standard output nor error includes the credential.

### Edge Cases

- A valid message body contains one or more `|` characters after the role separator.
- Input for separate work orders arrives rapidly or concurrently.
- The configured Anthropic credential is absent while no AI workflow step is enabled.
- Invalid framing, unknown work-order identifiers, end-of-input behavior, and terminal-result separators remain excluded pending explicit policy approval in `BUSINESS_RULES.md`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose this work as a separate implementation slice from the existing scheduling feature.
- **FR-002**: The system MUST receive valid participant messages in the binding format `<work_order_id>|<role> <message body>` and preserve the body exactly, including any later `|` characters.
- **FR-003**: The system MUST make each valid message available to the initial work-order workflow step asynchronously, without requiring a prior message for another work order to finish.
- **FR-004**: The initial workflow step MUST emit one complete, flushed outbound protocol block using the binding `WOID:<work_order_id>|ROLE:<role>` header and the received body.
- **FR-005**: The system MUST serialize complete outbound blocks so their lines never interleave.
- **FR-006**: The system MUST establish startup settings and explicitly injected dependencies once per process; workflow steps MUST NOT read environment variables directly.
- **FR-007**: The system MUST recognize `ANTHROPIC_API_KEY` as a startup credential, never include its value in protocol output, and not require it while no Anthropic workflow step is enabled.
- **FR-008**: The system MUST read the binding CSV once at startup, validate each work order, normalize reported timestamps to the startup local timezone, and start each valid WO with a Spanish handyman message.
- **FR-009**: The system MUST use `LOCAL_TIMEZONE`, defaulting to `Europe/Madrid`, as a validated startup-only IANA timezone.
- **FR-010**: The system MUST not assign behavior to malformed messages, unknown work-order IDs, EOF, or terminal separators until their pending policies are approved in `BUSINESS_RULES.md`.

### Key Entities *(include if feature involves data)*

- **Inbound Message**: A live participant message containing a work-order identifier, sender role, and complete body.
- **Outbound Message**: A complete, addressed protocol block emitted for a work order and recipient role.
- **Work-Order Workflow**: The independent asynchronous processing path that begins with the initial coordination node.
- **Runtime Settings**: The immutable startup configuration, including the optional Anthropic credential.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In automated tests, 100% of valid input lines are delivered with their exact bodies to the initial workflow step.
- **SC-002**: In automated tests, 100% of initial-step replies form a complete, non-interleaved outbound protocol block for the specified work order and role.
- **SC-003**: In automated tests, two valid work-order messages can both be accepted before either workflow is deliberately delayed by another order.
- **SC-004**: In tests with a configured credential, 0 credential values appear in standard output or error.

## Assumptions

- This slice reflects each valid received body rather than making scheduling, consent, availability, or terminal decisions.
- The binding role values are `tenant` and `handyman`.
- The coordinator retains a process-local asynchronous path per received work-order message; durable recovery is outside this slice.
- The external work-order CSV and all policy decisions not required for valid message reflection remain outside this task.

## Approved local development increment

The operator may select an alternate CSV path with `--csv` for local development. Omission keeps
the binding Docker input path unchanged. CSV validation, timezone normalization, startup messages,
and asynchronous stdin/stdout handling are identical in both environments.
