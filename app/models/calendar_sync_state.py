from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CalendarSyncState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calendar_id: str = ""
    calendar_summary: str = "Flights"
