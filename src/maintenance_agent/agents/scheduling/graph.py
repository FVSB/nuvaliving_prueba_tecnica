"""Wiring for the first compiled scheduling graph."""

import logging

from langgraph.graph import END, START, StateGraph

from maintenance_agent.agents.scheduling.nodes.initialize_coordination import (
    InitializeCoordinationNode,
)
from maintenance_agent.agents.scheduling.nodes.recognize_language import RecognizeLanguageNode
from maintenance_agent.agents.scheduling.state import SchedulingState
from maintenance_agent.application.language_recognition import LanguageRecognizer
from maintenance_agent.application.messages import OutboundMessage

logger = logging.getLogger(__name__)


def build_scheduling_graph(
    recognizer: LanguageRecognizer,
    initialize_node: InitializeCoordinationNode,
):
    """Compile the required recognition-before-initialization topology."""
    recognize_language = RecognizeLanguageNode(recognizer)

    async def initialize_coordination(state: SchedulingState) -> dict[str, OutboundMessage]:
        work_order = state["work_order"]
        logger.info(
            "[initialize_coordination] wo=%s node=initialize_coordination direction=in",
            work_order.work_order_id,
        )
        outbound = await initialize_node(work_order)
        logger.info(
            "[initialize_coordination] wo=%s node=initialize_coordination "
            "direction=out role=%s body=%r",
            work_order.work_order_id,
            outbound.role,
            outbound.body,
        )
        return {"outbound_message": outbound}

    graph = StateGraph(SchedulingState)
    graph.add_node("recognize_language", recognize_language)
    graph.add_node("initialize_coordination", initialize_coordination)
    graph.add_edge(START, "recognize_language")
    graph.add_edge("recognize_language", "initialize_coordination")
    graph.add_edge("initialize_coordination", END)
    return graph.compile()
