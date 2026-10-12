"""One-event negotiation transitions, independent of transport and graph runtime."""

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from maintenance_agent.application.conversation import (
    AvailabilityInterpretation,
    ConversationHandler,
    MessageClass,
    PartOfDay,
)
from maintenance_agent.application.messages import InboundMessage, OutboundMessage, TerminalFrame
from maintenance_agent.application.scheduling import CandidateAvailability
from maintenance_agent.application.slot_table import (
    SlotGridSpec,
    SlotTable,
    compose_slot_reply_text,
    derive_open_slots,
    describe_window,
    filter_slots,
    render_slot_fallback_reply,
    reply_embeds_table,
)
from maintenance_agent.domain.decisions import interpret_explicit_decision
from maintenance_agent.domain.languages import LanguageRecognitionResult
from maintenance_agent.domain.negotiation import (
    AvailabilityEvidence,
    DecisionValue,
    GraphCursor,
    ParticipantDecision,
    ParticipantRole,
    PendingAction,
    PendingQuestion,
    Proposal,
    ReviewCode,
    ReviewReason,
    TerminalStatus,
    TimeInterval,
    VisitCandidate,
)
from maintenance_agent.domain.scheduling import (
    check_visit_feasibility,
    common_windows,
    create_candidates,
    local_interval,
    urgency_comparison,
)
from maintenance_agent.domain.work_orders import WorkOrder
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority

SLOT_MAX_ATTEMPTS = 3

_LANGUAGES = {
    "es": "Spanish",
    "en": "English",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ca": "Catalan",
    "ar": "Arabic",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}


class NegotiationWorkflow:
    """Keeps conversation state per order and delegates all time arbitration to the authority."""

    def __init__(
        self,
        conversation: ConversationHandler,
        agenda: InMemoryScheduleAuthority,
        local_timezone: str = "Europe/Madrid",
        clock: Callable[[], datetime] | None = None,
        slot_grid: SlotGridSpec | None = None,
    ) -> None:
        self._conversation = conversation
        self._agenda = agenda
        self._timezone = local_timezone
        self._slot_grid = slot_grid or SlotGridSpec()
        self._clock = clock or (lambda: datetime.now(ZoneInfo(local_timezone)))

    async def start(self, work_order: WorkOrder, language: LanguageRecognitionResult) -> dict:
        lang = language.language_code.value
        state = {
            "work_order": work_order,
            "workflow_version": 1,
            "graph_cursor": GraphCursor.TENANT_AVAILABILITY,
            "tenant_language": lang,
            "terminal_status": None,
            "tenant_evidence": None,
            "handyman_evidence": None,
            "candidates": (),
            "proposal": None,
            "decisions": (),
            "pending_question": self._question(
                ParticipantRole.TENANT, PendingAction.TENANT_AVAILABILITY
            ),
            "finalization_pending": False,
            "confirmations_sent": frozenset(),
        }
        intro = await self._compose(
            "introduce the maintenance visit request and ask the tenant for all explicit "
            "availability intervals",
            lang,
            {
                "work_order": work_order.work_order,
                "address": work_order.address,
                "description": work_order.description,
                "reported_at": work_order.reported_at.isoformat(),
            },
        )
        return {
            **state,
            "outbound_message": OutboundMessage(work_order.work_order_id, "tenant", intro),
        }

    async def handle(self, state: dict, message: InboundMessage) -> dict:
        state = {**state, "outbound_message": None, "terminal_frame": None}
        if state.get("terminal_status") is not None:
            return state
        if message.body == "<NO RESPONSE>":
            question = state.get("pending_question")
            reason = ReviewReason(
                ReviewCode.NO_RESPONSE,
                "No response from "
                f"{message.role} while awaiting "
                f"{question.action.value if question else 'a reply'}.",
                ParticipantRole(message.role),
                state.get("graph_cursor"),
                question.question_id if question else None,
                tuple(state.get("tenant_evidence").intervals)
                if state.get("tenant_evidence")
                else (),
                timezone_name=self._timezone,
            )
            if await self._agenda.close_review(message.work_order_id, reason):
                return {
                    **state,
                    "terminal_status": TerminalStatus.REQUIRES_REVIEW,
                    "review_reason": reason,
                    "pending_question": None,
                    "outbound_message": None,
                    "terminal_frame": TerminalFrame(
                        message.work_order_id, "requires_review", f"REASON:{reason.render_line()}"
                    ),
                }
            return state

        question: PendingQuestion | None = state.get("pending_question")
        if question is None or question.role.value != message.role:
            return await self._clarify(
                state, ParticipantRole(message.role), "Please reply to the pending question."
            )
        if question.action in (
            PendingAction.TENANT_AVAILABILITY,
            PendingAction.SLOT_SUGGESTION,
            PendingAction.SLOT_FALLBACK,
        ):
            return await self._tenant_availability(state, message)
        if question.action is PendingAction.TENANT_ALTERNATIVES:
            return await self._alternatives(state, message)
        if question.action is PendingAction.DISPLACED_ALTERNATIVE:
            return await self._displaced_choice(state, message)
        if question.action is PendingAction.RELATIVE_DATE_CONFIRMATION:
            return await self._confirm_relative_date(state, message)
        if question.action is PendingAction.HANDYMAN_AVAILABILITY:
            return await self._handyman_availability(state, message)
        if question.action is PendingAction.TENANT_CONFIRMATION:
            return await self._confirmation(state, message, ParticipantRole.TENANT)
        if question.action is PendingAction.HANDYMAN_CONFIRMATION:
            return await self._confirmation(state, message, ParticipantRole.HANDYMAN)
        if question.action is PendingAction.HUMAN_SCHEDULING:
            return await self._human_choice(state, message)
        if question.action is PendingAction.AVAILABILITY_CHANGE:
            return await self._change_choice(state, message)
        return state

    async def _tenant_availability(self, state: dict, message: InboundMessage) -> dict:
        result = await self._conversation.interpret_availability(
            message.body, ParticipantRole.TENANT, self._clock(), self._timezone
        )
        if (
            result.classification is MessageClass.VAGUE_DATE_REQUEST
            and not result.intervals
            and not result.suggested_intervals
        ):
            return await self._slot_suggestion(state, result)
        if result.date_confirmation_required:
            if not result.suggested_intervals:
                return await self._ask(
                    state,
                    "tenant",
                    "clarify_relative_date",
                    result.clarification
                    or "Ask for the intended full calendar date and time range.",
                )
            state = {**state, "relative_date_intervals": result.suggested_intervals}
            proposed = self._format_windows(result.suggested_intervals)
            if result.weekday_is_today:
                date_instruction = (
                    "The tenant named the weekday that matches today. Say that a visit today "
                    "cannot be used, "
                    "then ask if the next occurrence below is what the tenant means."
                )
            else:
                date_instruction = "Ask the tenant to confirm the absolute local interval below."
            return await self._ask(
                state,
                "tenant",
                "confirm_relative_date",
                f"{date_instruction} Keep it as a suggestion until an explicit yes. "
                f"Proposed local interval: {proposed}",
                action=PendingAction.RELATIVE_DATE_CONFIRMATION,
            )
        if result.clarification_required or not result.complete or not result.intervals:
            return await self._ask(
                state,
                "tenant",
                "clarify_absolute_availability",
                result.clarification
                or "Ask for complete availability intervals with explicit calendar "
                "dates and times.",
            )
        previous = state.get("tenant_evidence")
        if previous is not None and previous.intervals != result.intervals:
            proposed = AvailabilityEvidence(
                state["work_order"].work_order_id,
                ParticipantRole.TENANT,
                result.intervals,
                previous.revision + 1,
                result.complete,
            )
            return await self._begin_availability_dispute(state, previous, proposed)
        return await self._record_tenant_intervals(state, result.intervals)

    async def _slot_suggestion(
        self, state: dict, interpretation: AvailabilityInterpretation
    ) -> dict:
        """Reply to a vague date request with a deterministic table and a validated intro/ask."""
        order: WorkOrder = state["work_order"]
        work_order_id = order.work_order_id
        lang = state["tenant_language"]
        language_name = _LANGUAGES.get(lang, lang)
        events: list[dict] = []
        reply: str | None = None
        feedback = ""
        request = (
            interpretation.date_from,
            interpretation.date_to,
            interpretation.part_of_day,
        )
        table = await self._open_slot_table(lang, *request)
        window = describe_window(*request, lang)
        for attempt in range(1, SLOT_MAX_ATTEMPTS + 1):
            verdict_valid, verdict_feedback, draft, diagnostic = await self._attempt_slot_reply(
                table, language_name, lang, feedback, window, request
            )
            attempt_detail: dict[str, object] = {
                "actor": "system",
                "attempt": attempt,
                "table_rows": len(table.slots),
                "valid": verdict_valid,
            }
            if diagnostic:
                attempt_detail["diagnostic"] = diagnostic
            events.append({"event_type": "slot_suggestion_attempt", "detail": attempt_detail})
            if verdict_valid:
                reply = draft
                break
            feedback = verdict_feedback
            events.append(
                {
                    "event_type": "slot_suggestion_feedback",
                    "detail": {"actor": "system", "attempt": attempt, "feedback": feedback},
                }
            )
        if reply is None:
            reply = render_slot_fallback_reply(lang, interpretation.ambiguity_reason)
            events.append(
                {
                    "event_type": "slot_fallback_emitted",
                    "detail": {
                        "actor": "system",
                        "ambiguity_reason": interpretation.ambiguity_reason.value,
                    },
                }
            )
        return {
            **state,
            "pending_question": self._question(
                ParticipantRole.TENANT, PendingAction.TENANT_AVAILABILITY
            ),
            "graph_cursor": GraphCursor.TENANT_AVAILABILITY,
            "outbound_message": OutboundMessage(work_order_id, "tenant", reply),
            "trace_events": events,
        }

    async def _open_slot_table(
        self,
        lang: str,
        date_from: str | None,
        date_to: str | None,
        part_of_day: PartOfDay,
    ) -> SlotTable:
        snapshot = await self._agenda.snapshot()
        now = self._clock()
        grid = self._slot_grid
        last = date_to or date_from
        if last:
            today = now.astimezone(ZoneInfo(self._timezone)).date()
            try:
                needed = (date.fromisoformat(last) - today).days + 1
            except ValueError:
                needed = 0
            grid = replace(grid, lookahead_days=min(max(grid.lookahead_days, needed), 35))
        slots = derive_open_slots(snapshot, now, self._timezone, grid)
        filtered = bool(date_from or date_to) or part_of_day is not PartOfDay.NONE
        return SlotTable(filter_slots(slots, date_from, date_to, part_of_day), lang, filtered)

    async def _attempt_slot_reply(
        self,
        table: SlotTable,
        language_name: str,
        lang: str,
        feedback: str,
        window: str,
        request: tuple[str | None, PartOfDay],
    ) -> tuple[bool, str, str, str]:
        """Compose once and gate it; return (valid, feedback, reply, diagnostic).

        The diagnostic is for traces only and is never fed back into the next prompt.
        """
        facts = {
            "table": table.render_markdown(),
            "window": window,
            "feedback": feedback,
            "language": language_name,
        }
        try:
            intro, ask = await self._conversation.compose_slot_reply(language_name, facts)
        except Exception as error:  # noqa: BLE001 - provider failure counts as a failed attempt
            return False, f"Composition failed: {type(error).__name__}.", "", str(error)
        reply = compose_slot_reply_text(intro, table, ask)
        if not intro.strip() or not ask.strip():
            return False, "Both an introduction and a closing ask are required.", reply, ""
        if not reply_embeds_table(reply, table):
            return False, "The table or disclaimer was altered.", reply, ""
        current = await self._open_slot_table(lang, *request)
        if current.render_markdown() != table.render_markdown():
            return False, "The shared agenda changed; slot openness no longer matches.", reply, ""
        try:
            verdict = await self._conversation.validate_slot_reply(reply, facts)
        except Exception as error:  # noqa: BLE001 - provider failure counts as invalid
            return False, f"Validation failed: {type(error).__name__}.", reply, str(error)
        if not verdict.valid:
            return (
                False,
                verdict.feedback or "The reply was rejected by the validator.",
                reply,
                verdict.diagnostic or "",
            )
        return True, "", reply, ""

    async def _record_tenant_intervals(
        self, state: dict, intervals: tuple[TimeInterval, ...]
    ) -> dict:
        order: WorkOrder = state["work_order"]
        evidence = AvailabilityEvidence(
            order.work_order_id,
            ParticipantRole.TENANT,
            intervals,
            state["workflow_version"] + 1,
            True,
        )
        candidates = create_candidates(order.work_order_id, intervals, evidence.revision)
        snapshot = await self._agenda.snapshot()
        incompatible_occupied = tuple(
            appointment.interval for appointment in snapshot.appointments
        ) + tuple(
            hold.interval
            for hold in snapshot.holds
            if hold.work_order_id == order.work_order_id
            or urgency_comparison(order.urgency, hold.urgency) <= 0
        )
        feasibility = {
            candidate.slot_id: check_visit_feasibility(
                candidate.interval, intervals, incompatible_occupied
            )
            for candidate in candidates
        }
        inspection = await self._agenda.inspect_candidates(candidates, order.urgency)
        blockers = tuple(
            f"{blocker.work_order_id}:{blocker.interval.start.isoformat()}/"
            f"{blocker.interval.end.isoformat()}"
            for item in inspection
            if item.availability is CandidateAvailability.BLOCKED
            for blocker in item.blockers
        )
        eligible = tuple(
            item.candidate
            for item in inspection
            if item.availability is not CandidateAvailability.BLOCKED
            and feasibility[item.candidate.slot_id].feasible
        )
        state = {
            **state,
            "tenant_evidence": evidence,
            "candidates": eligible,
            "all_tenant_candidates": candidates,
            "agenda_blockers": blockers,
            "slot_feasibility": {
                slot_id: (verdict.feasible, verdict.reasons)
                for slot_id, verdict in feasibility.items()
            },
            "workflow_version": evidence.revision,
        }
        await self._agenda.apply_availability_change(evidence)
        if not eligible:
            return await self._ask(
                state,
                "tenant",
                "request_tenant_alternatives",
                "Explain that every requested interval is blocked by the shared agenda and "
                "ask for alternatives or confirmation that the set is exhausted.",
                action=PendingAction.TENANT_ALTERNATIVES,
            )
        state["pending_question"] = self._question(
            ParticipantRole.HANDYMAN, PendingAction.HANDYMAN_AVAILABILITY
        )
        windows = self._format_windows(tuple(candidate.interval for candidate in eligible))
        body = await self._compose(
            "ask the handyman in Spanish whether any listed full two-hour candidate works",
            "es",
            {"candidates": windows},
        )
        return {
            **state,
            "graph_cursor": GraphCursor.HANDYMAN_AVAILABILITY,
            "outbound_message": OutboundMessage(order.work_order_id, "handyman", body),
        }

    async def _handyman_availability(self, state: dict, message: InboundMessage) -> dict:
        result = await self._conversation.interpret_availability(
            message.body, ParticipantRole.HANDYMAN, self._clock(), self._timezone
        )
        if result.clarification_required or not result.complete or not result.intervals:
            return await self._ask(
                state,
                "handyman",
                "clarify_handyman_availability",
                "Ask the handyman in Spanish to state complete absolute available intervals.",
            )
        order: WorkOrder = state["work_order"]
        revision = state["workflow_version"] + 1
        evidence = AvailabilityEvidence(
            order.work_order_id,
            ParticipantRole.HANDYMAN,
            result.intervals,
            revision,
            result.complete,
        )
        previous = state.get("handyman_evidence")
        if previous is not None and previous.intervals != evidence.intervals:
            return await self._begin_availability_dispute(
                state, previous, replace(evidence, revision=previous.revision + 1)
            )
        await self._agenda.apply_availability_change(evidence)
        tenant: AvailabilityEvidence = state["tenant_evidence"]
        union = common_windows(tenant.intervals, result.intervals)
        possible: list[VisitCandidate] = []
        for window in union:
            start = window.start
            while start + timedelta(hours=2) <= window.end:
                slot = TimeInterval(start, start + timedelta(hours=2))
                if not any(candidate.interval == slot for candidate in possible):
                    possible.append(
                        VisitCandidate(
                            f"counter:{order.work_order_id}:{start.isoformat()}",
                            order.work_order_id,
                            slot,
                            tenant.revision,
                            True,
                        )
                    )
                start += timedelta(hours=2)
        inspection = await self._agenda.inspect_candidates(tuple(possible), order.urgency)
        eligible = tuple(
            item.candidate
            for item in inspection
            if item.availability is not CandidateAvailability.BLOCKED
        )
        state = {
            **state,
            "handyman_evidence": evidence,
            "workflow_version": revision,
            "common_candidates": eligible,
        }
        if not eligible:
            reason = ReviewReason(
                ReviewCode.NO_COMMON_AVAILABILITY,
                "No mutually acceptable visit time: complete tenant and handyman availability "
                "has no common eligible two-hour interval.",
                tenant_windows=tenant.intervals,
                handyman_windows=result.intervals,
                timezone_name=self._timezone,
            )
            return await self._ask_human(state, reason)
        candidate = min(eligible, key=lambda item: (item.interval.start, item.slot_id))
        proposal = Proposal(
            uuid4().hex,
            (state.get("proposal").proposal_version + 1) if state.get("proposal") else 1,
            candidate,
            tenant.revision,
            evidence.revision,
            (await self._agenda.snapshot()).version,
        )
        state = {
            **state,
            "proposal": proposal,
            "pending_question": self._question(
                ParticipantRole.TENANT,
                PendingAction.TENANT_CONFIRMATION,
                proposal.proposal_id,
                proposal.proposal_version,
            ),
        }
        start, end = local_interval(candidate.interval, self._timezone)
        body = await self._compose(
            "ask the tenant to explicitly accept or reject this exact visit",
            state["tenant_language"],
            {"start": start.isoformat(), "end": end.isoformat()},
        )
        return {
            **state,
            "graph_cursor": GraphCursor.TENANT_CONFIRMATION,
            "outbound_message": OutboundMessage(order.work_order_id, "tenant", body),
        }

    async def _confirmation(
        self, state: dict, message: InboundMessage, role: ParticipantRole
    ) -> dict:
        proposal: Proposal = state["proposal"]
        decision = interpret_explicit_decision(message.body)
        if decision is None:
            return await self._ask(
                state,
                role.value,
                "clarify_confirmation",
                "Ask for an explicit yes or no to the exact proposed visit: "
                f"{self._slot_text(proposal.candidate)}",
            )
        if decision is DecisionValue.NO:
            await self._agenda.release_hold(message.work_order_id, proposal.proposal_id)
            return await self._ask(
                state,
                "tenant",
                "request_tenant_alternatives",
                "Ask the tenant for another explicit availability interval.",
                action=PendingAction.TENANT_ALTERNATIVES,
            )
        decision_record = ParticipantDecision(
            state["pending_question"].question_id,
            role,
            proposal.proposal_id,
            proposal.proposal_version,
            DecisionValue.YES,
        )
        decisions = state.get("decisions", ()) + (decision_record,)
        if role is ParticipantRole.TENANT:
            candidate = proposal.candidate
            held, displaced = await self._agenda.acquire_or_transfer_hold(
                candidate,
                state["work_order"].urgency,
                proposal.proposal_id,
                proposal.proposal_version,
            )
            if not held:
                return await self._ask(
                    state,
                    "tenant",
                    "request_tenant_alternatives",
                    "Explain that the shared agenda changed and ask for another interval.",
                    action=PendingAction.TENANT_ALTERNATIVES,
                )
            state = {**state, "displaced_work_orders": displaced, "decisions": decisions}
            state["pending_question"] = self._question(
                role=ParticipantRole.HANDYMAN,
                action=PendingAction.HANDYMAN_CONFIRMATION,
                proposal_id=proposal.proposal_id,
                proposal_version=proposal.proposal_version,
            )
            lang, recipient = "es", "handyman"
            intent = "ask the handyman for a separate explicit yes or no to the exact visit"
        else:
            prior = tuple(
                item
                for item in state.get("decisions", ())
                if item.proposal_id == proposal.proposal_id
                and item.proposal_version == proposal.proposal_version
                and item.decision is DecisionValue.YES
            )
            roles = {item.role for item in prior} | {role}
            if roles != {ParticipantRole.TENANT, ParticipantRole.HANDYMAN}:
                return await self._ask(
                    state,
                    "tenant",
                    "request_tenant_confirmation",
                    "Ask the tenant to confirm the exact visit before committing.",
                    action=PendingAction.TENANT_CONFIRMATION,
                )
            appointment = await self._agenda.commit_appointment(
                proposal.candidate,
                proposal.proposal_id,
                proposal.proposal_version,
                prior + (decision_record,),
            )
            if appointment is None:
                return await self._ask(
                    state,
                    "tenant",
                    "request_tenant_alternatives",
                    "Explain that the visit could not be committed because the agenda "
                    "changed and ask for availability.",
                    action=PendingAction.TENANT_ALTERNATIVES,
                )
            return await self._finalize(
                {
                    **state,
                    "decisions": prior + (decision_record,),
                    "terminal_status": TerminalStatus.SCHEDULED,
                    "finalization_pending": True,
                }
            )
        body = await self._compose(intent, lang, {"visit": self._slot_text(proposal.candidate)})
        return {
            **state,
            "graph_cursor": GraphCursor.HANDYMAN_CONFIRMATION,
            "outbound_message": OutboundMessage(state["work_order"].work_order_id, recipient, body),
        }

    async def _finalize(self, state: dict) -> dict:
        proposal: Proposal = state["proposal"]
        order: WorkOrder = state["work_order"]
        sent = set(state.get("confirmations_sent", frozenset()))
        for role, language in (
            (ParticipantRole.TENANT, state["tenant_language"]),
            (ParticipantRole.HANDYMAN, "es"),
        ):
            if role in sent:
                continue
            start, end = local_interval(proposal.candidate.interval, self._timezone)
            body = await self._compose(
                "confirm the scheduled visit",
                language,
                {"start": start.isoformat(), "end": end.isoformat()},
            )
            sent.add(role)
            state = {
                **state,
                "confirmations_sent": frozenset(sent),
                "outbound_message": OutboundMessage(order.work_order_id, role.value, body),
            }
            return state
        start, _ = local_interval(proposal.candidate.interval, self._timezone)
        return {
            **state,
            "finalization_pending": False,
            "outbound_message": None,
            "terminal_frame": TerminalFrame(
                order.work_order_id, "scheduled", f"SCHEDULED_FOR:{start.isoformat()}"
            ),
        }

    async def continue_finalization(self, state: dict) -> dict:
        """Continue already committed confirmation delivery after a later inbound turn."""
        if state.get("terminal_status") is not TerminalStatus.SCHEDULED:
            return state
        if not state.get("finalization_pending") and state.get("terminal_frame") is None:
            return state
        return await self._finalize(state)

    async def handle_displaced_hold(self, state: dict) -> dict:
        """Notify a displaced tenant with the earliest known eligible replacement."""
        order: WorkOrder = state["work_order"]
        known = await self._agenda.known_eligible_candidates(order.work_order_id, order.urgency)
        if not known:
            return await self._ask(
                state,
                "tenant",
                "displaced_hold_request_availability",
                "Explain that a higher-priority work order took the tentative visit and ask for all current availability.",
                action=PendingAction.TENANT_AVAILABILITY,
            )
        candidate = known[0]
        state = {**state, "displaced_candidate": candidate}
        start, end = local_interval(candidate.interval, self._timezone)
        body = await self._compose(
            "notify the tenant that their tentative visit was displaced and offer this earliest already-known eligible alternative",
            state["tenant_language"],
            {"start": start.isoformat(), "end": end.isoformat()},
        )
        return {
            **state,
            "pending_question": self._question(
                ParticipantRole.TENANT, PendingAction.DISPLACED_ALTERNATIVE
            ),
            "graph_cursor": GraphCursor.HANDLE_DISPLACED_HOLD,
            "outbound_message": OutboundMessage(order.work_order_id, "tenant", body),
        }

    async def _displaced_choice(self, state: dict, message: InboundMessage) -> dict:
        choice = interpret_explicit_decision(message.body)
        candidate: VisitCandidate = state["displaced_candidate"]
        if choice is None:
            return await self._ask(
                state,
                "tenant",
                "clarify_displaced_alternative",
                f"Ask whether the tenant is available for {self._slot_text(candidate)}.",
                action=PendingAction.DISPLACED_ALTERNATIVE,
            )
        if choice is DecisionValue.NO:
            return await self._ask(
                state,
                "tenant",
                "request_tenant_availability",
                "Ask for all current explicit availability intervals.",
                action=PendingAction.TENANT_AVAILABILITY,
            )
        tenant: AvailabilityEvidence = state["tenant_evidence"]
        handyman: AvailabilityEvidence = state["handyman_evidence"]
        proposal = Proposal(
            uuid4().hex,
            (state.get("proposal").proposal_version + 1) if state.get("proposal") else 1,
            candidate,
            tenant.revision,
            handyman.revision,
            await self.schedule_version(),
        )
        state = {**state, "proposal": proposal}
        return await self._ask(
            state,
            "tenant",
            "confirm_displaced_proposal",
            f"Ask for a separate explicit yes or no to the exact replacement visit {self._slot_text(candidate)}.",
            action=PendingAction.TENANT_CONFIRMATION,
        )

    async def schedule_version(self) -> int:
        return (await self._agenda.snapshot()).version

    async def _human_choice(self, state: dict, message: InboundMessage) -> dict:
        decision = interpret_explicit_decision(message.body)
        if decision is None:
            return await self._ask(
                state,
                "tenant",
                "clarify_human_scheduling",
                "Ask whether the tenant wants a human to arrange the visit.",
            )
        if decision is DecisionValue.YES:
            reason = state["review_reason"]
            closed = await self._agenda.close_review(state["work_order"].work_order_id, reason)
            if closed:
                frame = TerminalFrame(
                    state["work_order"].work_order_id,
                    "requires_review",
                    f"REASON:{reason.render_line()}",
                )
                return {
                    **state,
                    "terminal_status": TerminalStatus.REQUIRES_REVIEW,
                    "pending_question": None,
                    "outbound_message": None,
                    "terminal_frame": frame,
                }
        return await self._ask(
            state,
            "tenant",
            "request_tenant_availability",
            "Ask for new explicit availability intervals.",
            action=PendingAction.TENANT_AVAILABILITY,
        )

    async def _alternatives(self, state: dict, message: InboundMessage) -> dict:
        decision = interpret_explicit_decision(message.body)
        if decision is None:
            return await self._ask(
                state,
                "tenant",
                "clarify_tenant_alternatives",
                "Ask whether the tenant has other dates or has exhausted all availability.",
            )
        if decision is DecisionValue.YES:
            reason = ReviewReason(
                ReviewCode.NO_ELIGIBLE_SLOT,
                "No eligible visit time: all tenant-provided candidates are blocked by "
                "confirmed or equal/higher-priority agenda occupants.",
                tenant_windows=state["tenant_evidence"].intervals
                if state.get("tenant_evidence")
                else (),
                blockers=tuple(state.get("agenda_blockers", ())),
                timezone_name=self._timezone,
            )
            return await self._ask_human(state, reason)
        return await self._ask(
            state,
            "tenant",
            "request_tenant_availability",
            "Ask for additional explicit availability dates and times.",
            action=PendingAction.TENANT_AVAILABILITY,
        )

    async def _confirm_relative_date(self, state: dict, message: InboundMessage) -> dict:
        intervals = state.get("relative_date_intervals", ())
        label = self._format_windows(intervals) if intervals else "the proposed calendar date"
        result = interpret_explicit_decision(message.body)
        if result is None:
            return await self._ask(
                state,
                "tenant",
                "clarify_relative_date_confirmation",
                f"Ask whether {label} is correct, or request a full calendar date.",
                action=PendingAction.RELATIVE_DATE_CONFIRMATION,
            )
        if result is DecisionValue.NO:
            return await self._ask(
                state,
                "tenant",
                "request_explicit_calendar_date",
                "Ask for the full calendar date and availability times.",
                action=PendingAction.TENANT_AVAILABILITY,
            )
        if not intervals:
            return await self._ask(
                state,
                "tenant",
                "request_explicit_calendar_date",
                "Ask for the full calendar date and availability times.",
                action=PendingAction.TENANT_AVAILABILITY,
            )
        return await self._record_tenant_intervals(state, tuple(intervals))

    async def _change_choice(self, state: dict, message: InboundMessage) -> dict:
        dispute = state.get("disputed_availability")
        if dispute is None or dispute["role"].value != message.role:
            return state
        answer = interpret_explicit_decision(message.body)
        if answer is None:
            return await self._ask(
                state,
                message.role,
                "clarify_availability_change",
                "Ask whether the newly stated availability is correct: yes keeps the new "
                "interval, no keeps the previous interval.",
                action=PendingAction.AVAILABILITY_CHANGE,
            )
        chosen = (
            replace(dispute["proposed"], revision=dispute["proposed"].revision + 1, disputed=False)
            if answer is DecisionValue.YES
            else replace(
                dispute["previous"], revision=dispute["proposed"].revision + 1, disputed=False
            )
        )
        await self._agenda.apply_availability_change(chosen)
        state = {
            **state,
            "workflow_version": chosen.revision,
            "disputed_availability": None,
            "proposal": None,
            "decisions": (),
        }
        if dispute["role"] is ParticipantRole.TENANT:
            return await self._record_tenant_intervals(state, chosen.intervals)
        state["handyman_evidence"] = chosen
        return await self._ask(
            state,
            "tenant",
            "request_tenant_availability_confirmation",
            "Explain that handyman availability changed and ask the tenant to restate or "
            "confirm their availability.",
            action=PendingAction.TENANT_AVAILABILITY,
        )

    async def _begin_availability_dispute(self, state: dict, previous, proposed) -> dict:
        role = proposed.role
        suspended = replace(previous, revision=proposed.revision, disputed=True)
        await self._agenda.apply_availability_change(suspended)
        proposal = state.get("proposal")
        if proposal is not None:
            await self._agenda.release_hold(state["work_order"].work_order_id, proposal.proposal_id)
        state = {
            **state,
            "tenant_evidence": suspended
            if role is ParticipantRole.TENANT
            else state.get("tenant_evidence"),
            "handyman_evidence": suspended
            if role is ParticipantRole.HANDYMAN
            else state.get("handyman_evidence"),
            "proposal": None,
            "decisions": (),
            "workflow_version": proposed.revision,
            "disputed_availability": {"role": role, "previous": previous, "proposed": proposed},
        }
        return await self._ask(
            state,
            role.value,
            "confirm_availability_change",
            "Explain that this availability differs from the earlier statement and ask "
            "whether the new interval is correct.",
            action=PendingAction.AVAILABILITY_CHANGE,
        )

    async def _ask_human(self, state: dict, reason: ReviewReason) -> dict:
        state = {**state, "review_reason": reason}
        return await self._ask(
            state,
            "tenant",
            "offer_human_scheduling",
            "Explain the evidence-backed scheduling issue and ask whether the tenant wants "
            "human scheduling.",
            action=PendingAction.HUMAN_SCHEDULING,
        )

    async def _clarify(self, state: dict, role: ParticipantRole, intent: str) -> dict:
        return await self._ask(state, role.value, "clarification", intent)

    async def _ask(
        self,
        state: dict,
        role: str,
        intent: str,
        instruction: str,
        action: PendingAction | None = None,
    ) -> dict:
        recipient = ParticipantRole(role)
        language = "es" if recipient is ParticipantRole.HANDYMAN else state["tenant_language"]
        body = await self._compose(intent, language, {"instruction": instruction})
        action = (
            action
            or state.get(
                "pending_question", self._question(recipient, PendingAction.TENANT_AVAILABILITY)
            ).action
        )
        question = self._question(
            recipient,
            action,
            state.get("proposal").proposal_id if state.get("proposal") else None,
            state.get("proposal").proposal_version if state.get("proposal") else None,
        )
        return {
            **state,
            "pending_question": question,
            "graph_cursor": GraphCursor(action.value),
            "outbound_message": OutboundMessage(state["work_order"].work_order_id, role, body),
        }

    def _question(
        self,
        role: ParticipantRole,
        action: PendingAction,
        proposal_id: str | None = None,
        proposal_version: int | None = None,
    ) -> PendingQuestion:
        return PendingQuestion(uuid4().hex, role, action, 0, 0, proposal_id, proposal_version)

    async def _compose(self, intent: str, language: str, facts: dict[str, str]) -> str:
        if language == "undetermined":
            return (
                f"We can help with {facts.get('work_order', 'this maintenance request')}: "
                f"{facts.get('description', 'maintenance requested')} at "
                f"{facts.get('address', 'the provided address')}. "
                "Please share all dates and times when you are available. / "
                f"Podemos ayudarle con {facts.get('work_order', 'esta solicitud')}: "
                f"{facts.get('description', 'mantenimiento solicitado')} en "
                f"{facts.get('address', 'la dirección indicada')}. "
                "Indique todas las fechas y horas en que está disponible."
            )
        return await self._conversation.compose(intent, _LANGUAGES.get(language, language), facts)

    def _format_windows(self, intervals: tuple[TimeInterval, ...]) -> str:
        return "; ".join(self._slot_text(VisitCandidate("", "", item, 0)) for item in intervals)

    def _slot_text(self, candidate: VisitCandidate) -> str:
        start, end = local_interval(candidate.interval, self._timezone)
        return f"{start.isoformat()} to {end.isoformat()} ({self._timezone})"
