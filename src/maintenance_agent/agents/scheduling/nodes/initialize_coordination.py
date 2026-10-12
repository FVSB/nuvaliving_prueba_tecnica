"""First asynchronous scheduling-graph node."""

from maintenance_agent.application.messages import OutboundMessage
from maintenance_agent.domain.work_orders import WorkOrder


class InitializeCoordinationNode:
    """Issue the first Spanish notification for each validated work order."""

    async def __call__(self, work_order: WorkOrder) -> OutboundMessage:
        return OutboundMessage(
            work_order_id=work_order.work_order_id,
            role="tenant",
            body="Nueva orden de trabajo iniciada.",
        )
