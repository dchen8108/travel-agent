from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime

from app.catalog import airline_codes, airport_codes
from app.models.program import Program
from app.models.trip_instance import TripInstance
from app.route_details import (
    RankedRouteDetail,
    parse_route_detail_rankings,
    serialize_route_detail_rankings,
)
from app.services.ids import new_id
from app.services.trackers import sync_trackers
from app.services.trip_instances import generate_trip_instances as generate_trip_rows
from app.settings import get_settings

DEFAULT_LOOKAHEAD_WEEKS = 12

DEFAULT_PROGRAM_VALUES = {
    "program_name": "LA to SF Outbound",
    "route_detail_rankings": serialize_route_detail_rankings(
        [
            RankedRouteDetail(
                origin_airport="BUR",
                destination_airport="SFO",
                weekday="Monday",
                start_time="06:00",
                end_time="10:00",
                airline="Alaska",
                nonstop_only=True,
            )
        ]
    ),
}


class ProgramValidationError(ValueError):
    pass


def default_program() -> Program:
    return Program(program_id="draft", **DEFAULT_PROGRAM_VALUES)


def build_program(form: Mapping[str, str], existing: Program | None = None) -> Program:
    detail_source = str(form.get("route_detail_rankings", "")).strip()
    if not detail_source:
        detail_source = build_legacy_route_details_payload(form)

    route_detail_rankings = normalize_route_detail_rankings(detail_source)
    if not route_detail_rankings:
        raise ProgramValidationError("Add at least one ranked route detail.")

    incoming_program_id = str(form.get("program_id", "")).strip()
    if incoming_program_id == "draft":
        incoming_program_id = ""

    payload = {
        "program_id": incoming_program_id or (existing.program_id if existing else new_id("prog")),
        "program_name": str(form.get("program_name", "")).strip(),
        "active": coerce_checkbox(form, "active", default=True),
        "route_detail_rankings": route_detail_rankings,
    }

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


def normalize_route_detail_rankings(value: str) -> str:
    try:
        details = parse_route_detail_rankings(value)
    except ValueError as exc:
        raise ProgramValidationError("Route details must use supported airports, airlines, weekdays, and valid time ranges.") from exc
    if not details:
        return ""
    return serialize_route_detail_rankings(details)


def build_legacy_route_details_payload(form: Mapping[str, str]) -> str:
    origin_airports = normalize_supported_airport_list(str(form.get("origin_airports", "")))
    destination_airports = normalize_supported_airport_list(str(form.get("destination_airports", "")))
    weekdays = str(form.get("travel_weekday", "") or form.get("outbound_weekday", "")).strip()
    start_time = str(form.get("outbound_time_start", "")).strip()
    end_time = str(form.get("outbound_time_end", "")).strip()
    airline_tokens: list[str] = []
    for field_name in ("airline", "airlines", "preferred_airlines", "allowed_airlines"):
        raw_value = str(form.get(field_name, "")).strip()
        if not raw_value:
            continue
        for token in raw_value.replace(",", "|").split("|"):
            candidate = token.strip()
            if candidate and candidate not in airline_tokens:
                airline_tokens.append(candidate)
    airlines = normalize_supported_airline_list("|".join(airline_tokens))
    if not origin_airports or not destination_airports or not weekdays or not start_time or not end_time:
        return ""
    airline_values = airlines or [""]
    details: list[RankedRouteDetail] = []
    for origin_airport in origin_airports:
        for destination_airport in destination_airports:
            for airline in airline_values:
                details.append(
                    RankedRouteDetail(
                        origin_airport=origin_airport,
                        destination_airport=destination_airport,
                        weekday=weekdays,
                        start_time=start_time,
                        end_time=end_time,
                        airline=airline,
                        nonstop_only=coerce_checkbox(form, "nonstop_only", default=True),
                    )
                )
    return serialize_route_detail_rankings(details)


def normalize_supported_airport_list(value: str) -> list[str]:
    if not value:
        return []
    raw_parts = [part.strip() for part in value.replace(",", "|").split("|") if part.strip()]
    canonical_lookup = {allowed.upper(): allowed for allowed in airport_codes()}
    normalized: list[str] = []
    for part in raw_parts:
        candidate = canonical_lookup.get(part.upper())
        if candidate is None:
            raise ProgramValidationError("Choose a supported airport.")
        if candidate not in normalized:
            normalized.append(candidate)
    return normalized


def normalize_supported_airline_list(value: str) -> list[str]:
    if not value:
        return []
    raw_parts = [part.strip() for part in value.replace(",", "|").split("|") if part.strip()]
    canonical_lookup = {allowed.lower(): allowed for allowed in airline_codes()}
    normalized: list[str] = []
    for part in raw_parts:
        candidate = canonical_lookup.get(part.lower())
        if candidate is None:
            raise ProgramValidationError("Choose a supported airline.")
        if candidate not in normalized:
            normalized.append(candidate)
    return normalized


def coerce_checkbox(form: Mapping[str, str], field_name: str, *, default: bool) -> bool:
    if hasattr(form, "getlist"):
        values = [value for value in form.getlist(field_name) if value != ""]
        if not values:
            return default
        return values[-1] == "true"
    raw = form.get(field_name)
    if raw is None:
        return default
    return str(raw) == "true"


def generate_trip_instances(
    program: Program,
    *,
    today: date | None = None,
) -> tuple[list[TripInstance], list]:
    trips = generate_trip_rows(
        program,
        get_settings(),
        today=today,
        lookahead_weeks=DEFAULT_LOOKAHEAD_WEEKS,
    )
    trips, trackers = sync_trackers(
        trips,
        programs_by_id={program.program_id: program},
        today=today,
    )
    return trips, trackers
