from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from app.catalog import airport_codes, airline_codes, fare_preference_values
from app.models.base import TripMode
from app.models.program import Program
from app.models.trip_instance import TripInstance
from app.services.ids import new_id
from app.services.trackers import sync_trackers
from app.services.trip_instances import generate_trip_instances as generate_trip_rows
from app.settings import get_settings

DEFAULT_PROGRAM_VALUES = {
    "program_name": "LA to SF Outbound",
    "trip_mode": TripMode.ONE_WAY,
    "origin_airports": "BUR|LAX|SNA",
    "destination_airports": "SFO",
    "outbound_weekday": "Monday",
    "outbound_time_start": "06:00",
    "outbound_time_end": "10:00",
    "return_weekday": None,
    "return_time_start": "",
    "return_time_end": "",
    "preferred_airlines": "Alaska|United|Delta",
    "allowed_airlines": "Alaska|United|Delta|Southwest",
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
    trip_mode = form.get("trip_mode", str(existing.trip_mode) if existing else TripMode.ONE_WAY)
    try:
        normalized_trip_mode = TripMode(trip_mode)
    except ValueError as exc:
        raise ProgramValidationError("Choose a supported trip mode.") from exc
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
    preferred_airlines = normalize_supported_list(
        form.get("preferred_airlines", ""),
        airline_codes(),
        value_type="airline",
    )
    allowed_airlines = normalize_supported_list(
        form.get("allowed_airlines", ""),
        airline_codes(),
        value_type="airline",
    )
    fare_preference = form.get("fare_preference", "flexible").strip()
    if fare_preference not in fare_preference_values():
        raise ProgramValidationError("Choose a supported fare preference.")

    return_weekday = form.get("return_weekday", "").strip() or None
    return_time_start = form.get("return_time_start", "").strip()
    return_time_end = form.get("return_time_end", "").strip()
    if normalized_trip_mode == TripMode.ROUND_TRIP and not return_weekday:
        raise ProgramValidationError("Round-trip rules require a return day.")

    incoming_program_id = form.get("program_id", "").strip()
    if incoming_program_id == "draft":
        incoming_program_id = ""

    try:
        payload = {
            "program_id": incoming_program_id or (existing.program_id if existing else new_id("prog")),
            "program_name": form.get("program_name", "").strip(),
            "trip_mode": normalized_trip_mode,
            "active": coerce_checkbox(form, "active", default=True),
            "origin_airports": origin_airports,
            "destination_airports": destination_airports,
            "outbound_weekday": form.get("outbound_weekday", "Monday"),
            "outbound_time_start": form.get("outbound_time_start", "06:00"),
            "outbound_time_end": form.get("outbound_time_end", "10:00"),
            "return_weekday": return_weekday,
            "return_time_start": return_time_start,
            "return_time_end": return_time_end,
            "preferred_airlines": preferred_airlines,
            "allowed_airlines": allowed_airlines,
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


def normalize_pipe_list(value: str) -> str:
    parts = [part.strip().upper() for part in value.replace(",", "|").split("|") if part.strip()]
    return "|".join(parts)


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
    trips, trackers = sync_trackers(trips)
    return trips, trackers
