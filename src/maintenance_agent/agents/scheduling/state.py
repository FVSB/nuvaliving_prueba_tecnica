"""Typed state for the scheduling graph."""

from typing import NotRequired, TypedDict

from maintenance_agent.application.messages import OutboundMessage
from maintenance_agent.domain.languages import LanguageRecognitionResult
from maintenance_agent.domain.work_orders import WorkOrder


class SchedulingState(TypedDict):
    """State shared by the first scheduling-graph nodes."""

    work_order: WorkOrder
    language_recognition: NotRequired[LanguageRecognitionResult]
    outbound_message: NotRequired[OutboundMessage]
