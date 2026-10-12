"""First scheduling-graph node for work-order language recognition."""

from maintenance_agent.agents.scheduling.state import SchedulingState
from maintenance_agent.application.language_recognition import LanguageRecognizer
from maintenance_agent.domain.languages import LanguageRecognitionResult


class RecognizeLanguageNode:
    """Store a validated language result before coordination initialization."""

    def __init__(self, recognizer: LanguageRecognizer) -> None:
        self._recognizer = recognizer

    async def __call__(self, state: SchedulingState) -> dict[str, LanguageRecognitionResult]:
        """Recognize the raw description once and return the graph-state update."""
        result = await self._recognizer.recognize(state["work_order"].description)
        return {"language_recognition": result}
