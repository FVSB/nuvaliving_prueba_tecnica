from datetime import datetime, timezone

from maintenance_agent.application.coordinator import _extend_history
from maintenance_agent.application.messages import InboundMessage, OutboundMessage
from maintenance_agent.application.workflow import NegotiationWorkflow
from maintenance_agent.domain.negotiation import ParticipantRole
from maintenance_agent.prompts.interpret_availability import build_availability_prompt


def test_history_records_cleared_turn_and_reply() -> None:
    state = {
        "inbound_message": InboundMessage("WO-1", "tenant", "mañana temprano"),
        "outbound_message": OutboundMessage("WO-1", "tenant", "Tabla de horarios"),
    }
    assert _extend_history(state) == (
        ("participant", "tenant", "mañana temprano"),
        ("assistant", "tenant", "Tabla de horarios"),
    )


def test_blocked_turn_is_not_added_by_the_caller_and_history_is_capped() -> None:
    state = {
        "history": tuple(("participant", "tenant", str(i)) for i in range(20)),
        "inbound_message": InboundMessage("WO-1", "tenant", "x"),
    }
    assert len(_extend_history(state)) == 8


def test_history_is_filtered_per_role_and_reaches_the_prompt() -> None:
    state = {
        "history": (
            ("participant", "tenant", "mañana temprano"),
            ("participant", "handyman", "otro"),
        )
    }
    history = NegotiationWorkflow._history_for(state, ParticipantRole.TENANT)
    assert history == (("participant", "mañana temprano"),)
    prompt = build_availability_prompt(
        "mañana a las 10",
        ParticipantRole.TENANT,
        datetime(2026, 10, 12, tzinfo=timezone.utc),
        "Europe/Madrid",
        history,
    )
    assert "mañana temprano" in prompt
    assert "otro" not in prompt
