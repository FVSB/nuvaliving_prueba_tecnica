from io import StringIO

import pytest

from maintenance_agent.application.messages import OutboundMessage
from maintenance_agent.infrastructure.cli_transport import (
    AsyncStdoutWriter,
    InputFormatError,
    parse_inbound_message,
)


def test_parser_preserves_full_body_including_pipes() -> None:
    message = parse_inbound_message("WO-17|tenant availability | morning | afternoon")

    assert message.work_order_id == "WO-17"
    assert message.role == "tenant"
    assert message.body == "availability | morning | afternoon"


def test_parser_rejects_non_protocol_input() -> None:
    with pytest.raises(InputFormatError):
        parse_inbound_message("not protocol")


async def test_writer_emits_one_flushed_protocol_block() -> None:
    stream = StringIO()
    writer = AsyncStdoutWriter(stream)

    await writer.write(OutboundMessage("WO-17", "handyman", "hola | available"))

    assert stream.getvalue() == "WOID:WO-17|ROLE:handyman\nhola | available\n\n"


def test_protocol_messages_share_the_work_order_contract() -> None:
    inbound = parse_inbound_message("WO-17|tenant hello")
    outbound = OutboundMessage("WO-17", "tenant", "hello")

    from maintenance_agent.application.messages import WorkOrderMessage

    assert isinstance(inbound, WorkOrderMessage)
    assert isinstance(outbound, WorkOrderMessage)


def test_validator_accepts_no_response_sentinel_and_limit_length_body() -> None:
    from maintenance_agent.application.messages import InboundMessage
    from maintenance_agent.infrastructure.cli_transport import validate_inbound_line

    assert isinstance(validate_inbound_line("WO-1|tenant <NO RESPONSE>"), InboundMessage)
    assert isinstance(validate_inbound_line("WO-1|tenant " + "a" * 10, 10), InboundMessage)


@pytest.mark.parametrize("line", ["WO-1|tenant ", "WO-1|tenant    ", "WO-1|handyman"])
def test_validator_rejects_empty_body_keeping_sender(line: str) -> None:
    from maintenance_agent.application.messages import RejectedInbound
    from maintenance_agent.infrastructure.cli_transport import validate_inbound_line

    rejected = validate_inbound_line(line)

    assert isinstance(rejected, RejectedInbound)
    assert (rejected.work_order_id, rejected.reason) == ("WO-1", "empty_body")


def test_validator_rejects_too_long_body_with_truncated_preview() -> None:
    from maintenance_agent.application.messages import RejectedInbound
    from maintenance_agent.infrastructure.cli_transport import validate_inbound_line

    rejected = validate_inbound_line("WO-1|tenant " + "a" * 11, 10)

    assert isinstance(rejected, RejectedInbound)
    assert rejected.reason == "too_long"
    assert rejected.length == 11
    assert len(rejected.preview) == 11
    long = validate_inbound_line("WO-1|tenant " + "a" * 5000, 2000)
    assert isinstance(long, RejectedInbound)
    assert len(long.preview) == 200


@pytest.mark.parametrize("line", ["WO-1|admin x", "no pipe here", "", "|tenant x"])
def test_validator_raises_when_sender_cannot_be_identified(line: str) -> None:
    from maintenance_agent.infrastructure.cli_transport import validate_inbound_line

    with pytest.raises(InputFormatError):
        validate_inbound_line(line)


def test_rejection_notices_are_fixed_and_localized() -> None:
    from maintenance_agent.application.rejections import RejectionReason, render_rejection

    assert render_rejection(RejectionReason.TOO_LONG, "es", 2000) == (
        "Su mensaje supera el máximo de 2000 caracteres y no se ha procesado."
    )
    assert render_rejection(RejectionReason.EMPTY_BODY, "xx", 1).count(" / ") == 1
