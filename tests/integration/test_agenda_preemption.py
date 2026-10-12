from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from maintenance_agent.__main__ import run
from maintenance_agent.application.language_recognition import StaticLanguageRecognizer
from maintenance_agent.application.scheduling import CandidateAvailability
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.negotiation import (
    DecisionValue,
    ParticipantDecision,
    ParticipantRole,
    TimeInterval,
    VisitCandidate,
)
from maintenance_agent.domain.work_orders import Urgency
from maintenance_agent.infrastructure.in_memory_schedule import InMemoryScheduleAuthority
from tests.integration.fakes import FakeConversationHandler, FakeStdinReader

_NOW = datetime.fromisoformat("2026-10-16T12:00:00+02:00")


def candidate(order: str, hour: int) -> VisitCandidate:
    start = datetime(2026, 10, 20, hour, tzinfo=timezone.utc)
    return VisitCandidate(order, order, TimeInterval(start, start + timedelta(hours=2)), 1)


def acceptances(proposal: str) -> tuple:
    return (
        ParticipantDecision("q-tenant", ParticipantRole.TENANT, proposal, 1, DecisionValue.YES),
        ParticipantDecision("q-handyman", ParticipantRole.HANDYMAN, proposal, 1, DecisionValue.YES),
    )


@pytest.mark.asyncio
async def test_inspection_prefilters_equal_higher_and_confirmed_occupancy() -> None:
    agenda = InMemoryScheduleAuthority()
    assert (await agenda.acquire_or_transfer_hold(candidate("WO-HIGH", 9), Urgency.HIGH, "p1", 1))[
        0
    ]
    assert (
        await agenda.commit_appointment(candidate("WO-CRIT", 12), "p2", 1, acceptances("p2"))
        is None
    )
    inspected = await agenda.inspect_candidates((candidate("WO-LOW", 9),), Urgency.LOW)
    assert inspected[0].availability is CandidateAvailability.BLOCKED


@pytest.mark.asyncio
async def test_strictly_higher_candidate_is_preemptible_until_selected() -> None:
    agenda = InMemoryScheduleAuthority()
    assert (await agenda.acquire_or_transfer_hold(candidate("WO-LOW", 9), Urgency.LOW, "p1", 1))[0]
    inspected = await agenda.inspect_candidates((candidate("WO-CRIT", 9),), Urgency.CRITICAL)
    assert inspected[0].availability is CandidateAvailability.PREEMPTIBLE
    snapshot = await agenda.snapshot()
    assert [hold.work_order_id for hold in snapshot.holds] == ["WO-LOW"]
    ok, displaced = await agenda.acquire_or_transfer_hold(
        candidate("WO-CRIT", 9), Urgency.CRITICAL, "p2", 1
    )
    assert ok and displaced == ("WO-LOW",)


@pytest.mark.asyncio
async def test_displaced_order_receives_earliest_known_replacement(capsys, tmp_path, monkeypatch):
    start = datetime(2026, 10, 20, 7, tzinfo=timezone.utc)
    end = start + timedelta(hours=4)
    monkeypatch.setenv("TRACES_DIR", str(tmp_path / "traces"))
    await run(
        now=_NOW,
        csv_path=Path(__file__).resolve().parents[1] / "fixtures" / "work_orders.csv",
        stdin_reader=FakeStdinReader(
            [
                "WO-002|tenant available",
                "WO-002|handyman available",
                "WO-002|handyman yes",
                "WO-002|tenant yes",
                "WO-001|tenant available",
                "WO-001|handyman available",
                "WO-001|handyman yes",
                "WO-001|tenant yes",
                "WO-001|handyman yes",
            ]
        ),
        conversation_handler=FakeConversationHandler(
            availability={
                "tenant": ((start.isoformat(), end.isoformat()),),
                "handyman": ((start.isoformat(), end.isoformat()),),
            },
        ),
        language_recognizer=StaticLanguageRecognizer(
            LanguageRecognitionResult(language_code=LanguageCode.ENGLISH)
        ),
    )
    output = capsys.readouterr().out
    assert "notify the tenant that their tentative visit was displaced" in output
    assert "Tuesday 2026-10-20" in output and "'start': '11:00'" in output
    assert output.count("RESULT:scheduled") == 1
