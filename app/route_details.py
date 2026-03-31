from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator

from app.catalog import airline_codes, airport_codes
from app.models.base import ProgramWeekday


class RankedRouteDetail(BaseModel):
    origin_airport: str
    destination_airport: str
    weekday: ProgramWeekday
    start_time: str
    end_time: str
    airline: str = ""
    nonstop_only: bool = True

    @field_validator("origin_airport", "destination_airport")
    @classmethod
    def validate_airport(cls, value: str) -> str:
        airport = value.strip().upper()
        if airport not in airport_codes():
            raise ValueError("Choose a supported airport.")
        return airport

    @field_validator("airline")
    @classmethod
    def validate_airline(cls, value: str) -> str:
        airline = value.strip()
        if airline and airline not in airline_codes():
            raise ValueError("Choose a supported airline.")
        return airline

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
        airline = self.airline or "Any airline"
        return f"{self.origin_airport} -> {self.destination_airport} · {self.weekday} {self.start_time}-{self.end_time} · {airline}"

    @property
    def short_label(self) -> str:
        return f"{self.origin_airport} -> {self.destination_airport} · {self.weekday} {self.start_time}-{self.end_time}"

    @property
    def slug(self) -> str:
        weekday = str(self.weekday).lower()
        airline = (self.airline or "any").lower().replace(" ", "_")
        return "_".join(
            [
                self.origin_airport.lower(),
                self.destination_airport.lower(),
                weekday,
                self.start_time.replace(":", ""),
                self.end_time.replace(":", ""),
                airline,
            ]
        )


def parse_route_detail_rankings(raw: str | list[dict[str, Any]] | None) -> list[RankedRouteDetail]:
    if raw in ("", None):
        return []
    payload = raw
    if isinstance(raw, str):
        payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("Route detail rankings must be a list.")
    return [RankedRouteDetail.model_validate(item) for item in payload]


def serialize_route_detail_rankings(details: list[RankedRouteDetail]) -> str:
    return json.dumps(
        [detail.model_dump(mode="json") for detail in details],
        separators=(",", ":"),
    )


def route_detail_summary(raw: str) -> str:
    details = parse_route_detail_rankings(raw)
    if not details:
        return "No ranked details"
    if len(details) == 1:
        return details[0].short_label
    return f"{details[0].short_label} + {len(details) - 1} more"


def rank_label(rank: int) -> str:
    if rank <= 1:
        return "Primary"
    if rank == 2:
        return "Backup"
    return f"Fallback {rank - 1}"


def route_detail_label_from_fields(
    origin_airport: str,
    destination_airport: str,
    weekday: str,
    start_time: str,
    end_time: str,
    airline: str,
) -> str:
    airline_label = airline or "Any airline"
    if not weekday or not start_time or not end_time:
        return f"{origin_airport} -> {destination_airport} · {airline_label}"
    return f"{origin_airport} -> {destination_airport} · {weekday} {start_time}-{end_time} · {airline_label}"


def departure_time_from_time_line(time_line: str) -> str | None:
    if not time_line:
        return None
    first_part = time_line.split("–", 1)[0].strip().replace("+1", "")
    try:
        parsed = datetime.strptime(first_part, "%I:%M %p")
    except ValueError:
        return None
    return parsed.strftime("%H:%M")


def route_detail_matches_time_line(detail: RankedRouteDetail, time_line: str) -> bool:
    departure_time = departure_time_from_time_line(time_line)
    if departure_time is None:
        return False
    return detail.start_time <= departure_time <= detail.end_time


def route_detail_signature(detail: RankedRouteDetail) -> tuple[str, str, str, str, str, str, bool]:
    return (
        detail.origin_airport,
        detail.destination_airport,
        str(detail.weekday),
        detail.start_time,
        detail.end_time,
        detail.airline,
        detail.nonstop_only,
    )
