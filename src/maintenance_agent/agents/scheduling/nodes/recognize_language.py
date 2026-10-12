"""First scheduling-graph node for work-order language recognition."""

import logging

from maintenance_agent.agents.scheduling.state import SchedulingState
from maintenance_agent.application.language_recognition import LanguageRecognizer
from maintenance_agent.domain.languages import LanguageRecognitionResult

logger = logging.getLogger(__name__)


class RecognizeLanguageNode:
    """Store a validated language result before coordination initialization."""

    def __init__(self, recognizer: LanguageRecognizer) -> None:
        self._recognizer = recognizer

    async def __call__(self, state: SchedulingState) -> dict[str, LanguageRecognitionResult]:
        """Recognize the raw description once and return the graph-state update."""
        work_order = state["work_order"]
        result = await self._recognizer.recognize(work_order.description)
        logger.info(
            "[recognize_language] wo=%s node=recognize_language language=%s "
            "input_description=%r language %r recognized for the supplied description",
            work_order.work_order_id,
            result.language_code.value,
            work_order.description,
            result.language_code.value,
        )
        return {"language_recognition": result}
