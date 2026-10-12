from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from maintenance_agent.config import Settings
from maintenance_agent.domain.work_orders import Urgency, WorkOrder


def test_work_order_normalizes_reported_at_to_configured_timezone() -> None:
    work_order = WorkOrder.model_validate(
        {
            "work_order_id": "WO-001",
            "work_order": "Gas leak",
            "address": "24 Oak Street",
            "description": "Gas smell",
            "reported_at": "2026-10-07T07:15:00+00:00",
            "urgency": "Critical",
        },
        context={"local_timezone": "Europe/Madrid"},
    )

    assert work_order.reported_at == datetime(
        2026, 10, 7, 9, 15, tzinfo=work_order.reported_at.tzinfo
    )
    assert work_order.reported_at.astimezone(UTC) == datetime(2026, 10, 7, 7, 15, tzinfo=UTC)
    assert work_order.urgency is Urgency.CRITICAL


def test_work_order_rejects_naive_reported_at() -> None:
    with pytest.raises(ValidationError, match="UTC offset"):
        WorkOrder.model_validate(
            {
                "work_order_id": "WO-001",
                "work_order": "Gas leak",
                "address": "24 Oak Street",
                "description": "Gas smell",
                "reported_at": "2026-10-07T09:15:00",
                "urgency": "Critical",
            }
        )


def test_settings_validate_the_configured_timezone() -> None:
    assert Settings(local_timezone="Europe/Madrid").local_timezone == "Europe/Madrid"

    with pytest.raises(ValidationError, match="IANA timezone"):
        Settings(local_timezone="not-a-timezone")
