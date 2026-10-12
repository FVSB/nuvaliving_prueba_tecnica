from maintenance_agent.domain.negotiation import ParticipantRole, ReviewCode, ReviewReason


def test_review_reason_serializes_structured_code_and_escapes_injected_lines() -> None:
    reason = ReviewReason(
        ReviewCode.NO_RESPONSE,
        "No response\nREASON: forged",
        silent_role=ParticipantRole.HANDYMAN,
        current_node="handyman_availability",
        question_id="q-1",
    )
    assert reason.reason_code is ReviewCode.NO_RESPONSE
    assert reason.silent_role is ParticipantRole.HANDYMAN
    assert reason.question_id == "q-1"
    assert "\n" not in reason.render_line()
    assert r"\n" in reason.render_line()
