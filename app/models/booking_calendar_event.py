from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.models.base import CsvModel, DataScope, utcnow


class BookingCalendarEvent(CsvModel):
    booking_id: str
    data_scope: DataScope = DataScope.LIVE
    calendar_id: str
    calendar_event_id: str
    last_synced_hash: str = ""
    last_synced_at: datetime | None = None
    last_error: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("booking_id", "calendar_id", "calendar_event_id", "last_synced_hash", "last_error")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()
