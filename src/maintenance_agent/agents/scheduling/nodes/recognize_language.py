"""First scheduling-graph node for work-order language recognition."""

from maintenance_agent.agents.scheduling.state import SchedulingState
from maintenance_agent.application.language_recognition import LanguageRecognizer
from maintenance_agent.domain.languages import LanguageRecognitionResult
from maintenance_agent.infrastructure.trace_writer import TraceWriter


class RecognizeLanguageNode:
    """Store a validated language result before coordination initialization."""

    def __init__(self, recognizer: LanguageRecognizer, trace_writer: TraceWriter) -> None:
        self._recognizer = recognizer
        self._trace_writer = trace_writer

    async def __call__(self, state: SchedulingState) -> dict[str, LanguageRecognitionResult]:
        """Recognize the raw description once and return the graph-state update."""
        work_order = state["work_order"]
        result = await self._recognizer.recognize(work_order.description)
        self._trace_writer.write(
            event_type="language_recognized",
            work_order_id=work_order.work_order_id,
            detail={
                "node": "recognize_language",
                "language_code": result.language_code.value,
                "input_description": work_order.description,
            },
        )
        return {"language_recognition": result}