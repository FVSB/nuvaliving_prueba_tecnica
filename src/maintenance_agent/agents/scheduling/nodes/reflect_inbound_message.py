"""Temporary live-message node used before interpretation is implemented."""

from maintenance_agent.application.messages import InboundMessage, OutboundMessage
from maintenance_agent.infrastructure.trace_writer import TraceWriter


class ReflectInboundMessageNode:
    """Reflect a validated message while later scheduling nodes are introduced."""

    def __init__(self, trace_writer: TraceWriter) -> None:
        self._trace_writer = trace_writer

    async def __call__(self, message: InboundMessage) -> OutboundMessage:
        outbound = OutboundMessage(
            work_order_id=message.work_order_id,
            role=message.role,
            body=message.body,
        )
        self._trace_writer.write(
            event_type="inbound_reflected",
            work_order_id=message.work_order_id,
            detail={
                "node": "reflect_inbound_message",
                "direction": "out",
                "role": outbound.role,
                "body": outbound.body,
            },
        )
        return outbound