from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator

from app.models.base import ProgramWeekday


class RankedTimeSlot(BaseModel):
    weekday: ProgramWeekday
    start_time: str
    end_time: str

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        datetime.strptime(value, "%H:%M")
        return value

    @field_validator("end_time")
    @classmethod
    def validate_range(cls, value: str, info) -> str:
        start_time = info.data.get("start_time")
        if start_time and value <= start_time:
            raise ValueError("End time must be after start time.")
        return value

    @property
    def label(self) -> str:
        return f"{self.weekday} {self.start_time}-{self.end_time}"

    @property
    def slug(self) -> str:
        weekday = str(self.weekday).lower()
        return f"{weekday}_{self.start_time.replace(':', '')}_{self.end_time.replace(':', '')}"


def parse_time_slot_rankings(raw: str | list[dict[str, Any]] | None) -> list[RankedTimeSlot]:
    if raw in ("", None):
        return []
    payload = raw
    if isinstance(raw, str):
        payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("Time slot rankings must be a list.")
    return [RankedTimeSlot.model_validate(item) for item in payload]


def serialize_time_slot_rankings(slots: list[RankedTimeSlot]) -> str:
    return json.dumps(
        [slot.model_dump(mode="json") for slot in slots],
        separators=(",", ":"),
    )


def time_slot_summary(raw: str) -> str:
    slots = parse_time_slot_rankings(raw)
    if not slots:
        return "No time slots"
    if len(slots) == 1:
        return slots[0].label
    return f"{slots[0].label} + {len(slots) - 1} more"


def rank_label(rank: int) -> str:
    if rank <= 1:
        return "Primary"
    if rank == 2:
        return "Backup"
    return f"Fallback {rank - 1}"


def slot_label_from_fields(weekday: str, start_time: str, end_time: str) -> str:
    if not weekday or not start_time or not end_time:
        return "Time slot not configured"
    return f"{weekday} {start_time}-{end_time}"


def departure_time_from_time_line(time_line: str) -> str | None:
    if not time_line:
        return None
    first_part = time_line.split("–", 1)[0].strip().replace("+1", "")
    try:
        parsed = datetime.strptime(first_part, "%I:%M %p")
    except ValueError:
        return None
    return parsed.strftime("%H:%M")


def time_slot_matches_time_line(slot: RankedTimeSlot, time_line: str) -> bool:
    departure_time = departure_time_from_time_line(time_line)
    if departure_time is None:
        return False
    return slot.start_time <= departure_time <= slot.end_time
