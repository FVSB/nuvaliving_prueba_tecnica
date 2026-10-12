from types import SimpleNamespace

import pytest

from maintenance_agent.domain.negotiation import ParticipantRole
from maintenance_agent.infrastructure.anthropic_conversation import AnthropicConversationHandler


class FakeMessages:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.response)])


class FakeClient:
    def __init__(self, response: str) -> None:
        self.messages = FakeMessages(response)


@pytest.mark.asyncio
async def test_availability_interpreter_validates_absolute_aware_intervals() -> None:
    client = FakeClient(
        '{"intervals":[{"start":"2026-10-14T09:00:00+02:00",'
        '"end":"2026-10-14T13:00:00+02:00"}],"suggested_intervals":[],'
        '"complete":true,"clarification_required":false,"date_confirmation_required":false,'
        '"weekday_is_today":false,"clarification":""}'
    )
    result = await AnthropicConversationHandler(client).interpret_availability(
        "October 14, 9 to 13",
        ParticipantRole.TENANT,
        __import__("datetime").datetime(2026, 10, 12, 12),
        "Europe/Madrid",
    )
    assert result.complete is True
    assert result.intervals[0].start.isoformat() == "2026-10-14T07:00:00+00:00"
    assert client.messages.calls[0]["output_config"]["format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_malformed_provider_output_becomes_clarification_and_never_decision() -> None:
    client = FakeClient("not json")
    handler = AnthropicConversationHandler(client)
    availability = await handler.interpret_availability(
        "tomorrow morning",
        ParticipantRole.TENANT,
        __import__("datetime").datetime(2026, 10, 12, 12),
        "Europe/Madrid",
    )
    decision = await handler.interpret_decision("probably yes", ParticipantRole.TENANT)
    assert availability.clarification_required is True
    assert availability.intervals == ()
    assert decision.decision is None
    assert decision.clarification_required is True
