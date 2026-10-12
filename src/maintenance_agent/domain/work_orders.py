"""Validated work-order domain contracts."""

from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator


class Urgency(StrEnum):
    """The urgency values accepted by the work-order CSV contract."""

    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class WorkOrder(BaseModel):
    """One validated CSV row, normalized to the injected local timezone."""

    model_config = ConfigDict(frozen=True)

    work_order_id: str
    work_order: str
    address: str
    description: str
    reported_at: datetime
    urgency: Urgency

    @field_validator("reported_at")
    @classmethod
    def normalize_reported_at(
        cls,
        reported_at: datetime,
        info: ValidationInfo,
    ) -> datetime:
        """Preserve the instant while presenting it in the configured local zone."""
        if reported_at.tzinfo is None or reported_at.utcoffset() is None:
            raise ValueError("reported_at must include a UTC offset.")

        local_timezone = (info.context or {}).get("local_timezone", "Europe/Madrid")
        try:
            return reported_at.astimezone(ZoneInfo(local_timezone))
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown local timezone: {local_timezone}") from error
