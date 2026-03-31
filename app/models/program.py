from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.models.base import CsvModel, utcnow
from app.route_details import (
    RankedRouteDetail,
    parse_route_detail_rankings,
    route_detail_signature,
    serialize_route_detail_rankings,
)


class Program(CsvModel):
    program_id: str
    program_name: str
    active: bool = True
    route_detail_rankings: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)

        if not normalized.get("route_detail_rankings"):
            legacy_details = build_legacy_route_details(normalized)
            if legacy_details:
                normalized["route_detail_rankings"] = serialize_route_detail_rankings(legacy_details)

        return normalized

    @model_validator(mode="after")
    def validate_route_details(self) -> "Program":
        details = parse_route_detail_rankings(self.route_detail_rankings)
        if not details:
            raise ValueError("Rules require at least one ranked route detail.")
        seen_signatures: set[tuple[str, str, str, str, str, str, bool]] = set()
        for detail in details:
            signature = route_detail_signature(detail)
            if signature in seen_signatures:
                raise ValueError("Duplicate ranked route details are not allowed. Duplicate a row, then change at least one field before saving.")
            seen_signatures.add(signature)
        self.route_detail_rankings = serialize_route_detail_rankings(details)
        return self


def build_legacy_route_details(raw: dict[str, object]) -> list[RankedRouteDetail]:
    legacy_origins = split_pipe(str(raw.get("origin_airports", "") or ""))
    legacy_destinations = split_pipe(str(raw.get("destination_airports", "") or ""))
    if not legacy_origins or not legacy_destinations:
        return []

    airlines = merge_airlines(raw)
    airline_values = airlines or [""]
    details: list[RankedRouteDetail] = []

    if raw.get("route_detail_rankings"):
        try:
            return parse_route_detail_rankings(str(raw["route_detail_rankings"]))
        except ValueError:
            return []

    slot_rankings = parse_legacy_time_slots(raw)

    for slot in slot_rankings:
        for origin_airport in legacy_origins:
            for destination_airport in legacy_destinations:
                for airline in airline_values:
                    details.append(
                        RankedRouteDetail(
                            origin_airport=origin_airport,
                            destination_airport=destination_airport,
                            weekday=slot["weekday"],
                            start_time=slot["start_time"],
                            end_time=slot["end_time"],
                            airline=airline,
                            nonstop_only=coerce_bool(raw.get("nonstop_only"), default=True),
                        )
                    )
    return details


def parse_legacy_time_slots(raw: dict[str, object]) -> list[dict[str, str]]:
    import json

    if raw.get("time_slot_rankings"):
        try:
            payload = json.loads(str(raw["time_slot_rankings"]))
            if isinstance(payload, list):
                slots = []
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    weekday = str(item.get("weekday", "")).strip()
                    start_time = str(item.get("start_time", "")).strip()
                    end_time = str(item.get("end_time", "")).strip()
                    if weekday and start_time and end_time:
                        slots.append(
                            {
                                "weekday": weekday,
                                "start_time": start_time,
                                "end_time": end_time,
                            }
                        )
                if slots:
                    return slots
        except ValueError:
            pass

    weekday = str(raw.get("travel_weekday", "") or raw.get("outbound_weekday", "")).strip()
    start_time = str(raw.get("outbound_time_start", "") or "").strip()
    end_time = str(raw.get("outbound_time_end", "") or "").strip()
    if not weekday or not start_time or not end_time:
        return []
    return [{"weekday": weekday, "start_time": start_time, "end_time": end_time}]


def split_pipe(value: str) -> list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]


def merge_airlines(raw: dict[str, object]) -> list[str]:
    merged: list[str] = []
    for field in ("airline", "airlines", "preferred_airlines", "allowed_airlines"):
        for candidate in split_pipe(str(raw.get(field, "") or "")):
            if candidate not in merged:
                merged.append(candidate)
    return merged


def coerce_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    return str(value).lower() == "true"
