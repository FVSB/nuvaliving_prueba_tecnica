# Feature Specification: Infer Work-Order Language

**Feature Branch**: `003-infer-order-language`  
**Created**: 2026-10-12  
**Status**: Draft  
**Input**: User description: "Create the first LangGraph pipeline node to infer each work order description's language and assign an ISO language code, with a typed catalogue of common ISO codes, an undetermined value, and English variables and prompts."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Identify the language of a work order (Priority: P1)

When coordination starts for a work order, the coordinator identifies the language expressed in its description and records a standardized language code before any later tenant-facing step needs it.

**Why this priority**: Tenant communications must be prepared in the language of the order, as required by `BUSINESS_RULES.md`.

**Independent Test**: Submit work orders with clearly Spanish and clearly English descriptions and verify that each is assigned the corresponding standardized language code before later workflow processing.

**Acceptance Scenarios**:

1. **Given** a work order whose description is clearly in Spanish, **When** its workflow begins, **Then** it records the Spanish ISO 639-1 language code.
2. **Given** a work order whose description is clearly in English, **When** its workflow begins, **Then** it records the English ISO 639-1 language code.
3. **Given** a description in a supported common language, **When** its workflow begins, **Then** its recognized code belongs to the shared catalogue of common ISO 639-1 language codes.

---

### User Story 2 - Preserve uncertainty safely (Priority: P2)

When the description does not contain enough reliable language evidence, the coordinator records an explicit undetermined result instead of guessing.

**Why this priority**: An inaccurate language assignment could cause the tenant to receive a message in the wrong language.

**Independent Test**: Submit an empty, mixed, or non-linguistic description and verify that it receives the undetermined value rather than a language code.

**Acceptance Scenarios**:

1. **Given** an empty or non-linguistic description, **When** its workflow begins, **Then** it records the explicit undetermined language value.
2. **Given** a description for which a single language cannot be determined reliably, **When** its workflow begins, **Then** it records the explicit undetermined language value and does not select a language arbitrarily.

### Edge Cases

- The description is empty, whitespace-only, or composed only of identifiers, numbers, and punctuation.
- The description mixes language fragments such that a single language cannot be determined reliably.
- The description is in a language outside the common-code catalogue.
- A recognized language other than Spanish or English is recorded for future handling; this feature does not alter the binding tenant-message policy.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST perform language recognition as the first processing step for every valid work order before later coordination actions.
- **FR-002**: The system MUST inspect the work-order description as the input for language recognition.
- **FR-003**: The system MUST record a recognized language as an ISO 639-1 code drawn from a shared catalogue of common language codes.
- **FR-004**: The shared catalogue MUST include at least the common languages Spanish, English, French, German, Italian, Portuguese, Dutch, Catalan, Arabic, Chinese, Japanese, and Korean.
- **FR-005**: The system MUST provide one explicit undetermined value for descriptions whose language cannot be inferred reliably.
- **FR-006**: The system MUST not substitute a guessed language when recognition is indeterminate.
- **FR-007**: All newly introduced internal names, variables, user-facing model instructions, and prompt text for this feature MUST be written in English.
- **FR-008**: The system MUST retain the recognition result in the work-order workflow state so subsequent steps can use it without reinterpreting the description.
- **FR-009**: This feature MUST honor the user-approved tenant-language-inference decision in `docs/decisions/004-tenant-language-inference.md` and MUST NOT alter the binding policy that tenant messages are Spanish or English without a separately approved policy change.

### Key Entities *(include if feature involves data)*

- **Work Order**: The incoming maintenance request whose description supplies the language evidence.
- **Language Code Catalogue**: The shared set of common ISO 639-1 codes available to the workflow.
- **Language Recognition Result**: Either one catalogue code or the explicit undetermined value, retained for the active work order.
- **Workflow State**: The per-work-order processing state that stores the language recognition result for later coordination nodes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Automated tests classify 100% of clearly Spanish and English fixture descriptions with their expected ISO 639-1 codes.
- **SC-002**: Automated tests classify 100% of empty, non-linguistic, and intentionally indeterminate fixture descriptions as undetermined.
- **SC-003**: Automated tests verify that 100% of recognition results are either a value in the common-code catalogue or the explicit undetermined value.
- **SC-004**: Automated tests verify that the language result is available to the next workflow step without evaluating the description again.

## Assumptions

- ISO 639-1 two-letter codes are the standard representation for this feature.
- The common-code catalogue is a reusable internal vocabulary, not a promise that every listed language will immediately receive tenant-facing messages.
- Spanish and English remain the currently approved tenant-message languages under `BUSINESS_RULES.md`.
- The user instruction authorizes tenant-language inference; the decision record captures the scope and rationale required by the binding business rules.
