"""Temporary live-message node used before interpretation is implemented."""

import logging

from maintenance_agent.application.messages import InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)


class ReflectInboundMessageNode:
    """Reflect a validated message while later scheduling nodes are introduced."""

    async def __call__(self, message: InboundMessage) -> OutboundMessage:
        outbound = OutboundMessage(
            work_order_id=message.work_order_id,
            role=message.role,
            body=message.body,
        )
        logger.info(
            "[reflect_inbound_message] wo=%s node=reflect_inbound_message "
            "direction=out role=%s body=%r",
            message.work_order_id,
            outbound.role,
            outbound.body,
        )
        return outbound
