"""Compiled graph wiring for one retained negotiation transition at a time."""

from langgraph.graph import END, START, StateGraph

from maintenance_agent.agents.scheduling.nodes.initialize_coordination import (
    InitializeCoordinationNode,
)
from maintenance_agent.agents.scheduling.nodes.injection_guard import InjectionGuardNode
from maintenance_agent.agents.scheduling.state import SchedulingState
from maintenance_agent.application.language_recognition import LanguageRecognizer
from maintenance_agent.application.messages import OutboundMessage
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.work_orders import WorkOrder
from maintenance_agent.infrastructure.trace_writer import TraceWriter


def build_scheduling_graph(
    recognizer: LanguageRecognizer,
    initialize_node: InitializeCoordinationNode,
    trace_writer: TraceWriter,
    workflow: NegotiationWorkflow | None = None,
    guard_node: InjectionGuardNode | None = None,
):
    """Build a single-step graph; the coordinator owns per-order checkpoint state.

    When ``guard_node`` is given, every inbound participant message passes through it first.
    """

    async def transition(state: SchedulingState) -> dict:
        work_order: WorkOrder = state["work_order"]
        updates: dict = {}
        language = state.get("language_recognition")
        if language is None:
            language = await recognizer.recognize(work_order.description)
            updates["language_recognition"] = language
            trace_writer.write(
                event_type="language_recognized",
                work_order_id=work_order.work_order_id,
                detail={
                    "actor": "system",
                    "language_code": language.language_code.value,
                    "input_description": work_order.description,
                },
            )

        if workflow is None:
            trace_writer.write(
                event_type="initialize_coordination_entered",
                work_order_id=work_order.work_order_id,
                detail={"node": "initialize_coordination", "direction": "in"},
            )
            outbound: OutboundMessage = await initialize_node(work_order)
            updates["outbound_message"] = outbound
            trace_writer.write(
                event_type="initialize_coordination_completed",
                work_order_id=work_order.work_order_id,
                detail={
                    "node": "initialize_coordination",
                    "direction": "out",
                    "role": outbound.role,
                    "body": outbound.body,
                },
            )
            return updates

        context = {**state, **updates}
        if state.get("resume_finalization"):
            result = await workflow.continue_finalization(context)
        elif state.get("retry_event"):
            result = await workflow.handle_retry(context, state["retry_event"])
        elif state.get("displaced_hold_event"):
            result = await workflow.handle_displaced_hold(context)
        elif state.get("inbound_message") is not None:
            result = await workflow.handle(context, state["inbound_message"])
        else:
            result = await workflow.start(work_order, language)
        for evidence_key, role in (
            ("tenant_evidence", "tenant"),
            ("handyman_evidence", "handyman"),
        ):
            evidence = result.get(evidence_key)
            if evidence is not None and evidence != state.get(evidence_key):
                trace_writer.write(
                    event_type="availability_evidence_recorded",
                    work_order_id=work_order.work_order_id,
                    detail={
                        "actor": role,
                        "revision": evidence.revision,
                        "complete": evidence.complete,
                        "disputed": evidence.disputed,
                        "intervals": [
                            {"start": item.start.isoformat(), "end": item.end.isoformat()}
                            for item in evidence.intervals
                        ],
                    },
                )
        prior_decisions = state.get("decisions", ())
        current_decisions = result.get("decisions", ())
        for decision in current_decisions[len(prior_decisions) :]:
            trace_writer.write(
                event_type="participant_decision_recorded",
                work_order_id=work_order.work_order_id,
                detail={
                    "actor": decision.role.value,
                    "question_id": decision.question_id,
                    "proposal_id": decision.proposal_id,
                    "proposal_version": decision.proposal_version,
                    "decision": decision.decision.value if decision.decision else None,
                },
            )
        displaced = tuple(result.get("displaced_work_orders", ()))
        if displaced:
            proposal = result.get("proposal")
            trace_writer.write(
                event_type="hold_transferred",
                work_order_id=work_order.work_order_id,
                detail={
                    "actor": "tenant",
                    "proposal_id": proposal.proposal_id if proposal else None,
                    "proposal_version": proposal.proposal_version if proposal else None,
                    "interval": {
                        "start": proposal.candidate.interval.start.isoformat(),
                        "end": proposal.candidate.interval.end.isoformat(),
                    }
                    if proposal
                    else None,
                    "displaced_work_orders": list(displaced),
                    "schedule_version": await workflow.schedule_version(),
                },
            )
        trace_writer.write(
            event_type="workflow_transition",
            work_order_id=work_order.work_order_id,
            detail={
                "actor": state.get("inbound_message").role
                if state.get("inbound_message")
                else "system",
                "node": result.get("graph_cursor", "start"),
                "workflow_version": result.get("workflow_version", 0),
                "schedule_version": await workflow.schedule_version(),
                "terminal_status": result.get("terminal_status").value
                if result.get("terminal_status") is not None
                else None,
            },
        )
        for event in result.pop("trace_events", ()):
            trace_writer.write(
                event_type=event["event_type"],
                work_order_id=work_order.work_order_id,
                detail=event["detail"],
            )
        result.pop("work_order", None)
        return {**updates, **result}

    graph = StateGraph(SchedulingState)
    graph.add_node("negotiation_transition", transition)
    if guard_node is None:
        graph.add_edge(START, "negotiation_transition")
    else:
        graph.add_node("injection_guard", guard_node)
        graph.add_conditional_edges(
            START,
            lambda state: (
                "injection_guard"
                if state.get("inbound_message") is not None
                else "negotiation_transition"
            ),
            ["injection_guard", "negotiation_transition"],
        )
        graph.add_conditional_edges(
            "injection_guard",
            lambda state: END if state.get("guard_blocked") else "negotiation_transition",
            [END, "negotiation_transition"],
        )
    graph.add_edge("negotiation_transition", END)
    return graph.compile()
