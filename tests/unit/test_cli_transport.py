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
