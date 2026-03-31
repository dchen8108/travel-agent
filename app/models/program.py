from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.models.base import CsvModel, utcnow
from app.time_slots import RankedTimeSlot, parse_time_slot_rankings, serialize_time_slot_rankings


class Program(CsvModel):
    program_id: str
    program_name: str
    active: bool = True
    origin_airports: str
    destination_airports: str
    time_slot_rankings: str
    airlines: str = ""
    fare_preference: str = "flexible"
    nonstop_only: bool = True
    lookahead_weeks: int = 8
    rebook_alert_threshold: int = 20
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)

        if not normalized.get("time_slot_rankings"):
            weekday = normalized.get("travel_weekday") or normalized.get("outbound_weekday")
            start_time = normalized.get("outbound_time_start")
            end_time = normalized.get("outbound_time_end")
            if weekday and start_time and end_time:
                slot = RankedTimeSlot(
                    weekday=weekday,
                    start_time=start_time,
                    end_time=end_time,
                )
                normalized["time_slot_rankings"] = serialize_time_slot_rankings([slot])

        if not normalized.get("airlines"):
            merged_airlines: list[str] = []
            for field in ("preferred_airlines", "allowed_airlines"):
                raw = normalized.get(field, "")
                for value in str(raw).split("|"):
                    candidate = value.strip()
                    if candidate and candidate not in merged_airlines:
                        merged_airlines.append(candidate)
            normalized["airlines"] = "|".join(merged_airlines)

        return normalized

    @model_validator(mode="after")
    def validate_slot_rankings(self) -> "Program":
        slots = parse_time_slot_rankings(self.time_slot_rankings)
        if not slots:
            raise ValueError("Rules require at least one ranked time slot.")
        self.time_slot_rankings = serialize_time_slot_rankings(slots)
        return self
