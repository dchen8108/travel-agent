from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.models.base import CsvModel, ProgramWeekday, TripMode, utcnow


class Program(CsvModel):
    program_id: str
    program_name: str
    active: bool = True
    trip_mode: TripMode = TripMode.ROUND_TRIP
    origin_airports: str
    destination_airports: str
    outbound_weekday: ProgramWeekday
    outbound_time_start: str
    outbound_time_end: str
    return_weekday: ProgramWeekday | None = None
    return_time_start: str = ""
    return_time_end: str = ""
    preferred_airlines: str = ""
    allowed_airlines: str = ""
    fare_preference: str = "flexible"
    nonstop_only: bool = True
    lookahead_weeks: int = 8
    rebook_alert_threshold: int = 20
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="before")
    @classmethod
    def normalize_optional_fields(cls, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if normalized.get("return_weekday") == "":
            normalized["return_weekday"] = None
        return normalized

    @model_validator(mode="after")
    def validate_mode_fields(self) -> "Program":
        if self.trip_mode == TripMode.ROUND_TRIP and self.return_weekday is None:
            raise ValueError("Round-trip rules require a return weekday.")
        if self.trip_mode == TripMode.ONE_WAY:
            self.return_weekday = None
            self.return_time_start = ""
            self.return_time_end = ""
        return self
