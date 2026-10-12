"""Graph node that screens every inbound participant message before any workflow logic."""

from dataclasses import replace

from maintenance_agent.agents.scheduling.state import SchedulingState
from maintenance_agent.application.injection_guard import (
    GuardAction,
    InjectionGuard,
    render_security_notice,
)
from maintenance_agent.application.messages import OutboundMessage
from maintenance_agent.infrastructure.trace_writer import TraceWriter

NO_RESPONSE_SENTINEL = "<NO RESPONSE>"


class InjectionGuardNode:
    """Pass, pass a cleaned body, or answer with a security notice plus the last question.

    A classifier failure fails open: the deterministic validation downstream still applies, and
    the error is recorded in the runtime trace.
    """

    def __init__(
        self, guard: InjectionGuard, trace_writer: TraceWriter, runtime_writer: TraceWriter
    ) -> None:
        self._guard = guard
        self._trace_writer = trace_writer
        self._runtime_writer = runtime_writer

    async def __call__(self, state: SchedulingState) -> dict:
        message = state["inbound_message"]
        work_order_id = message.work_order_id
        if not message.body.strip() or message.body == NO_RESPONSE_SENTINEL:
            return {"guard_blocked": False}
        try:
            decision = await self._guard.screen(message.body)
        except Exception as error:  # noqa: BLE001 - guard is best effort; downstream rules remain
            self._runtime_writer.write(
                event_type="injection_guard_error",
                work_order_id=work_order_id,
                detail={"error_type": type(error).__name__, "message": str(error)[:500]},
            )
            return {"guard_blocked": False}
        self._trace_writer.write(
            event_type="injection_guard_screened",
            work_order_id=work_order_id,
            detail={
                "actor": message.role,
                "action": decision.action.value,
                "reason": decision.reason,
                "fragment": decision.fragment,
                "stages": [
                    {
                        "stage": stage.stage,
                        "answer_yes": stage.answer_yes,
                        "probability_yes": stage.probability_yes,
                    }
                    for stage in decision.stages
                ],
            },
        )
        if decision.action is GuardAction.PASS:
            return {"guard_blocked": False}
        if decision.action is GuardAction.PASS_CLEANED:
            return {
                "guard_blocked": False,
                "inbound_message": replace(message, body=decision.body),
            }
        language = "es" if message.role == "handyman" else state.get("tenant_language", "")
        body = render_security_notice(language)
        last_question = (state.get("last_outbound") or {}).get(message.role)
        if last_question:
            body = f"{body}\n\n{last_question}"
        return {
            "guard_blocked": True,
            "outbound_message": OutboundMessage(work_order_id, message.role, body),
        }
