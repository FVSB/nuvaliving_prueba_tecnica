from maintenance_agent.agents.scheduling.nodes.recognize_language import RecognizeLanguageNode
from maintenance_agent.agents.scheduling.state import SchedulingState
from maintenance_agent.application.language_recognition import StaticLanguageRecognizer
from maintenance_agent.domain.languages import LanguageCode, LanguageRecognitionResult
from maintenance_agent.domain.work_orders import Urgency, WorkOrder


def work_order(description: str) -> WorkOrder:
    return WorkOrder.model_validate(
        {
            "work_order_id": "WO-1",
            "work_order": "Leak",
            "address": "1 Main Street",
            "description": description,
            "reported_at": "2026-10-07T09:15:00+02:00",
            "urgency": Urgency.HIGH,
        }
    )


async def test_node_adds_validated_language_result_to_state() -> None:
    result = LanguageRecognitionResult(language_code=LanguageCode.SPANISH)
    node = RecognizeLanguageNode(StaticLanguageRecognizer(result))
    state: SchedulingState = {"work_order": work_order("Hay una fuga de agua.")}

    update = await node(state)

    assert update["language_recognition"].language_code is LanguageCode.SPANISH


async def test_node_preserves_undetermined_result() -> None:
    result = LanguageRecognitionResult(language_code=LanguageCode.UNDETERMINED)
    node = RecognizeLanguageNode(StaticLanguageRecognizer(result))

    update = await node({"work_order": work_order("12345 !!!")})

    assert update["language_recognition"].language_code is LanguageCode.UNDETERMINED
