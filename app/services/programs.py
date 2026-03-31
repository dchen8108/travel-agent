from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from app.models.program import Program
from app.models.trip_instance import TripInstance
from app.services.ids import new_id
from app.services.trackers import sync_trackers
from app.services.trip_instances import generate_trip_instances as generate_trip_rows
from app.settings import get_settings

DEFAULT_PROGRAM_VALUES = {
    "program_name": "LA to SF Weekly Commute",
    "origin_airports": "BUR|LAX|SNA",
    "destination_airports": "SFO",
    "outbound_weekday": "Monday",
    "outbound_time_start": "06:00",
    "outbound_time_end": "10:00",
    "return_weekday": "Wednesday",
    "return_time_start": "16:00",
    "return_time_end": "21:00",
    "preferred_airlines": "Alaska|United|Delta",
    "allowed_airlines": "Alaska|United|Delta|Southwest",
    "fare_preference": "flexible",
    "nonstop_only": "true",
    "lookahead_weeks": "8",
    "rebook_alert_threshold": "20",
}


def default_program() -> Program:
    return Program(program_id="draft", **DEFAULT_PROGRAM_VALUES)


def build_program(form: Mapping[str, str], existing: Program | None = None) -> Program:
    payload = {
        "program_id": existing.program_id if existing else new_id("prog"),
        "program_name": form.get("program_name", "").strip(),
        "active": form.get("active", "true") == "true",
        "origin_airports": normalize_pipe_list(form.get("origin_airports", "")),
        "destination_airports": normalize_pipe_list(form.get("destination_airports", "")),
        "outbound_weekday": form.get("outbound_weekday", "Monday"),
        "outbound_time_start": form.get("outbound_time_start", "06:00"),
        "outbound_time_end": form.get("outbound_time_end", "10:00"),
        "return_weekday": form.get("return_weekday", "Wednesday"),
        "return_time_start": form.get("return_time_start", "16:00"),
        "return_time_end": form.get("return_time_end", "21:00"),
        "preferred_airlines": normalize_pipe_list(form.get("preferred_airlines", "")),
        "allowed_airlines": normalize_pipe_list(form.get("allowed_airlines", "")),
        "fare_preference": form.get("fare_preference", "flexible"),
        "nonstop_only": form.get("nonstop_only", "false") == "true",
        "lookahead_weeks": int(form.get("lookahead_weeks", "8") or 8),
        "rebook_alert_threshold": int(form.get("rebook_alert_threshold", "20") or 20),
    }
    if existing is not None:
        payload["created_at"] = existing.created_at
    return Program.model_validate(payload)


def normalize_pipe_list(value: str) -> str:
    parts = [part.strip().upper() for part in value.replace(",", "|").split("|") if part.strip()]
    return "|".join(parts)


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
