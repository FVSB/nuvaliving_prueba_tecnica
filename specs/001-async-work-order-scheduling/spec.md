# Feature Specification: Async Work-Order Scheduling

**Feature Branch**: `develop`
**Created**: 2026-10-12
**Status**: Draft
**Input**: User description: "Async CSV work-order ingestion, tenant prioritization, and
non-overlapping two-hour scheduling for one handyman."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Import Work Orders Safely (Priority: P1)

An operations user provides a CSV containing work orders (WOs) from several tenants. The system
accepts valid rows asynchronously, assigns every accepted WO to its tenant, and reports rows
that cannot be processed without preventing valid rows from continuing.

**Why this priority**: Scheduling cannot begin until the system has trustworthy work orders and
their tenant context.

**Independent Test**: Upload a CSV with valid WOs for two tenants and one malformed row. Verify
that both valid WOs are available for scheduling and the malformed row is reported without
exposing either tenant's data to the other.

**Acceptance Scenarios**:

1. **Given** a CSV with valid WOs for multiple tenants, **When** import starts, **Then** each
   accepted WO is associated with its source tenant and has a visible import outcome.
2. **Given** a CSV with a malformed or incomplete row, **When** import starts, **Then** that row
   is rejected with a reason and valid rows continue.
3. **Given** an imported WO, **When** a tenant views its work, **Then** it can view only WOs
   belonging to that tenant.

---

### User Story 2 - Prioritize and Reserve a Service Slot (Priority: P1)

An operations user asks the system to schedule eligible imported WOs. The system processes WOs
by priority and then submission order, reserves a two-hour service slot for the single handyman,
and records the outcome for the WO's tenant.

**Why this priority**: It realizes the product's central value: fair, conflict-free scheduling
across multiple tenants.

**Independent Test**: Import eligible WOs with different priorities and requested times, run
scheduling, and verify that the highest-priority feasible WO is booked first and no two accepted
bookings overlap.

**Acceptance Scenarios**:

1. **Given** eligible WOs with different priorities, **When** scheduling runs, **Then** the
   system considers the highest priority first and uses submission order to break a tie.
2. **Given** a feasible requested service time, **When** the slot is reserved, **Then** the
   appointment lasts exactly two hours and belongs to the WO's tenant.
3. **Given** a slot already held or confirmed for the handyman, **When** another WO requests an
   overlapping time, **Then** the system does not create a second appointment.

---

### User Story 3 - Track Asynchronous Scheduling Outcomes (Priority: P2)

An operations user can see whether a WO is awaiting import, awaiting scheduling, held,
scheduled, rejected, or needs review. The system records why a WO could not advance so it can be
retried or corrected without duplicating a booking.

**Why this priority**: Asynchronous processing needs clear outcomes before the workflow gains
additional decision nodes or tenant communications.

**Independent Test**: Submit a conflicting WO and a valid WO, then verify that each receives a
durable, tenant-scoped outcome with enough information to retry safely.

**Acceptance Scenarios**:

1. **Given** an asynchronous import or scheduling run, **When** it completes or fails, **Then**
   the WO displays its current outcome and the recorded reason.
2. **Given** a WO awaiting review because its requested time is unavailable, **When** it is
   retried without a schedule change, **Then** no duplicate appointment is created.

### Edge Cases

- A CSV repeats a WO identifier in the same file or a prior import.
- A priority is missing or outside the accepted range.
- The requested start time is invalid, ambiguous, in the past, or cannot form a two-hour slot.
- Two workers attempt to reserve the same available time concurrently.
- An import or scheduling run is interrupted after a hold but before its final result is recorded.
- A tenant attempts to query, retry, or alter another tenant's WO.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST ingest a CSV asynchronously and provide a distinct outcome for
  every row.
- **FR-002**: The system MUST require each accepted WO to include a unique source identifier,
  tenant identifier, priority, requested service start time, and tenant contact or destination.
- **FR-003**: The system MUST validate tenant scope before storing, viewing, retrying, or
  scheduling a WO.
- **FR-004**: The system MUST order eligible WOs by priority and then original submission order;
  the initial priority ordering is critical, high, normal, low.
- **FR-005**: The system MUST reserve exactly two hours for every accepted service appointment.
- **FR-006**: The system MUST treat the single handyman as capacity one and atomically prevent
  overlapping held or confirmed appointments.
- **FR-007**: The system MUST persist the WO outcome, its transition history, and any rejection
  or review reason so interrupted work can be resumed safely.
- **FR-008**: The system MUST make import and scheduling processing idempotent for the same WO
  identifier and request, preventing duplicate WOs and appointments.
- **FR-009**: The system MUST expose the current tenant-scoped WO and appointment outcome to an
  authorized operations user.
- **FR-010**: The workflow MUST identify its state fields, transitions, retry behavior, and
  failure outcome for each incremental scheduling node.
- **FR-011**: Any AI-assisted workflow step MUST validate its result before it affects a WO and
  MUST NOT decide tenant authorization, priority, availability, or appointment conflicts.

### Key Entities *(include if feature involves data)*

- **Tenant**: The organization that owns one or more WOs and can access only its own work.
- **Work Order**: An imported tenant request with its source identifier, priority, requested
  time, contact destination, import result, scheduling outcome, and transition history.
- **Handyman**: The sole shared service resource with capacity one.
- **Appointment Hold**: A temporary reservation for the handyman during asynchronous processing.
- **Appointment**: A confirmed two-hour service commitment for one WO and tenant.
- **Workflow Run**: The durable execution record for a WO's asynchronous processing and retry.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A 1,000-row well-formed CSV reaches a recorded row-level outcome within five
  minutes under normal operating conditions.
- **SC-002**: 100% of valid imported WOs retain their original tenant association, and an
  unauthorized cross-tenant read or mutation succeeds 0% of the time in acceptance tests.
- **SC-003**: 100% of accepted appointments occupy exactly two hours and no two accepted
  appointments for the handyman overlap in concurrency acceptance tests.
- **SC-004**: For a set of feasible WOs submitted together, the system schedules the highest
  priority first and respects submission order for equal priorities in 100% of acceptance tests.
- **SC-005**: An operations user can determine the outcome and next action for at least 95% of
  rejected or review-needed WOs without inspecting internal execution records.

## Assumptions

- The CSV is supplied by an authorized operations process and uses a documented UTF-8 header
  format.
- The first increment supports a single requested service window per WO; alternative-slot
  negotiation and tenant messaging are later workflow nodes.
- All service times are normalized and stored in UTC; the operations process supplies the
  presentation timezone.
- Priority values are critical, high, normal, and low; unspecified priorities are rejected.
- Authentication and authorization integration is supplied by the host application; this feature
  defines the tenant-scoping behavior it must enforce.
- CSV parsing, prioritization, availability validation, reservation, and outcome recording are
  the first workflow nodes. AI-assisted interpretation is deferred until a future slice needs it.
