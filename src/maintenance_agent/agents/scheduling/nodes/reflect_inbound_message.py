"""Temporary live-message node used before interpretation is implemented."""

from maintenance_agent.application.messages import InboundMessage, OutboundMessage


class ReflectInboundMessageNode:
    """Reflect a validated message while later scheduling nodes are introduced."""

    async def __call__(self, message: InboundMessage) -> OutboundMessage:
        return OutboundMessage(
            work_order_id=message.work_order_id,
            role=message.role,
            body=message.body,
        )
