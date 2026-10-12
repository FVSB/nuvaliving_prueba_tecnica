"""Wiring for the first compiled scheduling graph."""

from langgraph.graph import END, START, StateGraph

from maintenance_agent.agents.scheduling.nodes.initialize_coordination import (
    InitializeCoordinationNode,
)
from maintenance_agent.agents.scheduling.nodes.recognize_language import RecognizeLanguageNode
from maintenance_agent.agents.scheduling.state import SchedulingState
from maintenance_agent.application.language_recognition import LanguageRecognizer
from maintenance_agent.application.messages import OutboundMessage


def build_scheduling_graph(
    recognizer: LanguageRecognizer,
    initialize_node: InitializeCoordinationNode,
):
    """Compile the required recognition-before-initialization topology."""
    recognize_language = RecognizeLanguageNode(recognizer)

    async def initialize_coordination(state: SchedulingState) -> dict[str, OutboundMessage]:
        return {"outbound_message": await initialize_node(state["work_order"])}

    graph = StateGraph(SchedulingState)
    graph.add_node("recognize_language", recognize_language)
    graph.add_node("initialize_coordination", initialize_coordination)
    graph.add_edge(START, "recognize_language")
    graph.add_edge("recognize_language", "initialize_coordination")
    graph.add_edge("initialize_coordination", END)
    return graph.compile()
