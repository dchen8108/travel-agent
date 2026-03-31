from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import CsvModel, ProgramWeekday, utcnow


class Program(CsvModel):
    program_id: str
    program_name: str
    active: bool = True
    origin_airports: str
    destination_airports: str
    outbound_weekday: ProgramWeekday
    outbound_time_start: str
    outbound_time_end: str
    return_weekday: ProgramWeekday
    return_time_start: str
    return_time_end: str
    preferred_airlines: str = ""
    allowed_airlines: str = ""
    fare_preference: str = "flexible"
    nonstop_only: bool = True
    lookahead_weeks: int = 8
    rebook_alert_threshold: int = 20
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
