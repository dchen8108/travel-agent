from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime

from app.catalog import airport_codes, airline_codes, fare_preference_values
from app.models.program import Program
from app.models.trip_instance import TripInstance
from app.services.ids import new_id
from app.services.trackers import sync_trackers
from app.services.trip_instances import generate_trip_instances as generate_trip_rows
from app.settings import get_settings
from app.time_slots import RankedTimeSlot, parse_time_slot_rankings, serialize_time_slot_rankings

DEFAULT_PROGRAM_VALUES = {
    "program_name": "LA to SF Outbound",
    "origin_airports": "BUR|LAX|SNA",
    "destination_airports": "SFO",
    "time_slot_rankings": serialize_time_slot_rankings(
        [
            RankedTimeSlot(weekday="Monday", start_time="06:00", end_time="10:00"),
        ]
    ),
    "airlines": "Alaska|United|Delta",
    "fare_preference": "flexible",
    "nonstop_only": "true",
    "lookahead_weeks": "8",
    "rebook_alert_threshold": "20",
}


class ProgramValidationError(ValueError):
    pass


def default_program() -> Program:
    return Program(program_id="draft", **DEFAULT_PROGRAM_VALUES)


def build_program(form: Mapping[str, str], existing: Program | None = None) -> Program:
    origin_airports = normalize_supported_list(
        form.get("origin_airports", ""),
        airport_codes(),
        value_type="airport",
    )
    if not origin_airports:
        raise ProgramValidationError("Choose at least one origin airport.")
    destination_airports = normalize_supported_list(
        form.get("destination_airports", ""),
        airport_codes(),
        value_type="airport",
    )
    if not destination_airports:
        raise ProgramValidationError("Choose at least one destination airport.")

    airline_source = merge_airline_inputs(form)
    airlines = normalize_supported_list(
        airline_source,
        airline_codes(),
        value_type="airline",
    )

    fare_preference = form.get("fare_preference", "flexible").strip()
    if fare_preference not in fare_preference_values():
        raise ProgramValidationError("Choose a supported fare preference.")

    time_slot_source = str(form.get("time_slot_rankings", "")).strip()
    if not time_slot_source:
        legacy_weekday = form.get("travel_weekday", "") or form.get("outbound_weekday", "")
        legacy_start = form.get("outbound_time_start", "")
        legacy_end = form.get("outbound_time_end", "")
        if legacy_weekday and legacy_start and legacy_end:
            time_slot_source = serialize_time_slot_rankings(
                [
                    RankedTimeSlot(
                        weekday=legacy_weekday,
                        start_time=legacy_start,
                        end_time=legacy_end,
                    )
                ]
            )

    time_slot_rankings = normalize_time_slot_rankings(time_slot_source)
    if not time_slot_rankings:
        raise ProgramValidationError("Add at least one ranked time slot.")

    incoming_program_id = str(form.get("program_id", "")).strip()
    if incoming_program_id == "draft":
        incoming_program_id = ""

    try:
        payload = {
            "program_id": incoming_program_id or (existing.program_id if existing else new_id("prog")),
            "program_name": str(form.get("program_name", "")).strip(),
            "active": coerce_checkbox(form, "active", default=True),
            "origin_airports": origin_airports,
            "destination_airports": destination_airports,
            "time_slot_rankings": time_slot_rankings,
            "airlines": airlines,
            "fare_preference": fare_preference,
            "nonstop_only": coerce_checkbox(form, "nonstop_only", default=False),
            "lookahead_weeks": int(form.get("lookahead_weeks", "8") or 8),
            "rebook_alert_threshold": int(form.get("rebook_alert_threshold", "20") or 20),
        }
    except ValueError as exc:
        raise ProgramValidationError("Enter valid numeric values for lookahead and alert threshold.") from exc

    if existing is not None:
        payload["created_at"] = existing.created_at

    try:
        return Program.model_validate(payload)
    except ValueError as exc:
        raise ProgramValidationError(str(exc)) from exc


def duplicate_program(existing: Program) -> Program:
    now = datetime.now().astimezone()
    return existing.model_copy(
        update={
            "program_id": new_id("prog"),
            "program_name": f"{existing.program_name} Copy",
            "created_at": now,
            "updated_at": now,
        }
    )


def normalize_supported_list(value: str, allowed_values: set[str], value_type: str) -> str:
    if not value:
        return ""
    raw_parts = [part.strip() for part in value.replace(",", "|").split("|") if part.strip()]
    canonical_lookup = (
        {allowed.upper(): allowed for allowed in allowed_values}
        if value_type == "airport"
        else {allowed.lower(): allowed for allowed in allowed_values}
    )
    normalized_parts: list[str] = []
    for part in raw_parts:
        key = part.upper() if value_type == "airport" else part.lower()
        normalized = canonical_lookup.get(key)
        if normalized is None:
            raise ProgramValidationError(f"Choose a supported {value_type}.")
        if normalized not in normalized_parts:
            normalized_parts.append(normalized)
    return "|".join(normalized_parts)


def merge_airline_inputs(form: Mapping[str, str]) -> str:
    merged: list[str] = []
    for field in ("airlines", "preferred_airlines", "allowed_airlines"):
        raw = str(form.get(field, "") or "")
        for part in raw.replace(",", "|").split("|"):
            candidate = part.strip()
            if candidate and candidate not in merged:
                merged.append(candidate)
    return "|".join(merged)


def normalize_time_slot_rankings(value: str) -> str:
    try:
        slots = parse_time_slot_rankings(value)
    except ValueError as exc:
        raise ProgramValidationError("Time slots must be valid weekday and time ranges.") from exc
    return serialize_time_slot_rankings(slots)


def coerce_checkbox(form: Mapping[str, str], field_name: str, *, default: bool) -> bool:
    if hasattr(form, "getlist"):
        values = [value for value in form.getlist(field_name) if value != ""]
        if not values:
            return default
        return values[-1] == "true"
    raw = form.get(field_name)
    if raw is None:
        return default
    return raw == "true"


def generate_trip_instances(
    program: Program,
    *,
    lookahead_weeks: int | None = None,
    today: date | None = None,
) -> tuple[list[TripInstance], list]:
    effective_program = (
        program.model_copy(update={"lookahead_weeks": lookahead_weeks})
        if lookahead_weeks is not None
        else program
    )
    trips = generate_trip_rows(
        effective_program,
        get_settings(),
        today=today,
    )
    trips, trackers = sync_trackers(
        trips,
        programs_by_id={effective_program.program_id: effective_program},
        today=today,
    )
    return trips, trackers
