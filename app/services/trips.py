from __future__ import annotations

from datetime import date

from app.models.route_option import RouteOption
from app.models.trip import Trip
from app.models.base import RoutePreferenceMode, TripKind, utcnow
from app.services.ids import new_id
from app.storage.repository import Repository


def parse_trip_kind(raw: str) -> TripKind:
    return TripKind(raw)


def parse_preference_mode(raw: str) -> RoutePreferenceMode:
    return RoutePreferenceMode(raw)


def ensure_unique_trip_label(trips: list[Trip], label: str, *, existing_trip_id: str | None = None) -> None:
    normalized = label.strip().lower()
    for trip in trips:
        if existing_trip_id and trip.trip_id == existing_trip_id:
            continue
        if trip.label.strip().lower() == normalized:
            raise ValueError("Trip labels must be unique.")


def build_trip(
    *,
    trip_id: str | None,
    label: str,
    trip_kind: str,
    active: bool,
    anchor_date: date | None,
    anchor_weekday: str,
    preference_mode: str = RoutePreferenceMode.EQUAL,
) -> Trip:
    now = utcnow()
    return Trip(
        trip_id=trip_id or new_id("trip"),
        label=label,
        trip_kind=parse_trip_kind(trip_kind),
        preference_mode=parse_preference_mode(preference_mode),
        active=active,
        anchor_date=anchor_date,
        anchor_weekday=anchor_weekday,
        created_at=now,
        updated_at=now,
    )


def build_route_options(
    *,
    trip_id: str,
    payloads: list[dict[str, object]],
    existing_route_options: list[RouteOption] | None = None,
) -> list[RouteOption]:
    existing_by_id = {option.route_option_id: option for option in existing_route_options or []}
    built: list[RouteOption] = []
    seen_signatures: set[tuple[str, str, str, int, str, str]] = set()
    for index, payload in enumerate(payloads, start=1):
        route_option_id = str(payload.get("route_option_id") or "").strip() or new_id("opt")
        original = existing_by_id.get(route_option_id)
        option = RouteOption(
            route_option_id=route_option_id,
            trip_id=trip_id,
            rank=index,
            savings_needed_vs_previous=0 if index == 1 else int(payload.get("savings_needed_vs_previous", 0)),
            origin_airports=str(payload.get("origin_airports", "")),
            destination_airports=str(payload.get("destination_airports", "")),
            airlines=str(payload.get("airlines", "")),
            day_offset=int(payload.get("day_offset", 0)),
            start_time=str(payload.get("start_time", "")),
            end_time=str(payload.get("end_time", "")),
            created_at=original.created_at if original else utcnow(),
            updated_at=utcnow(),
        )
        signature = (
            option.origin_airports,
            option.destination_airports,
            option.airlines,
            option.day_offset,
            option.start_time,
            option.end_time,
        )
        if signature in seen_signatures:
            raise ValueError("Duplicate route options are not allowed.")
        seen_signatures.add(signature)
        built.append(option)
    if not built:
        raise ValueError("Trips require at least one route option.")
    return built


def save_trip(
    repository: Repository,
    *,
    trip_id: str | None,
    label: str,
    trip_kind: str,
    active: bool,
    anchor_date: date | None,
    anchor_weekday: str,
    route_option_payloads: list[dict[str, object]],
    preference_mode: str = RoutePreferenceMode.EQUAL,
) -> Trip:
    trips = repository.load_trips()
    route_options = repository.load_route_options()
    ensure_unique_trip_label(trips, label, existing_trip_id=trip_id)

    existing_trip = next((trip for trip in trips if trip.trip_id == trip_id), None) if trip_id else None
    trip = build_trip(
        trip_id=trip_id,
        label=label,
        trip_kind=trip_kind,
        preference_mode=preference_mode,
        active=active,
        anchor_date=anchor_date,
        anchor_weekday=anchor_weekday,
    )
    if existing_trip:
        trip.created_at = existing_trip.created_at
        trip.updated_at = utcnow()

    existing_route_options = [option for option in route_options if option.trip_id == trip.trip_id]
    built_route_options = build_route_options(
        trip_id=trip.trip_id,
        payloads=route_option_payloads,
        existing_route_options=existing_route_options,
    )

    repository.save_trips([item for item in trips if item.trip_id != trip.trip_id] + [trip])
    repository.save_route_options([item for item in route_options if item.trip_id != trip.trip_id] + built_route_options)
    return trip


def save_past_trip(
    repository: Repository,
    *,
    trip_id: str | None,
    label: str,
    anchor_date: date,
) -> Trip:
    trips = repository.load_trips()
    ensure_unique_trip_label(trips, label, existing_trip_id=trip_id)

    existing_trip = next((trip for trip in trips if trip.trip_id == trip_id), None) if trip_id else None
    trip = build_trip(
        trip_id=trip_id,
        label=label,
        trip_kind=TripKind.ONE_TIME,
        preference_mode=RoutePreferenceMode.EQUAL,
        active=True,
        anchor_date=anchor_date,
        anchor_weekday="",
    )
    if existing_trip:
        trip.created_at = existing_trip.created_at
        trip.updated_at = utcnow()

    repository.save_trips([item for item in trips if item.trip_id != trip.trip_id] + [trip])
    return trip


def set_trip_active(repository: Repository, trip_id: str, active: bool) -> Trip:
    trips = repository.load_trips()
    trip = next((item for item in trips if item.trip_id == trip_id), None)
    if trip is None:
        raise KeyError("Trip not found")
    trip.active = active
    trip.updated_at = utcnow()
    repository.save_trips(trips)
    return trip


def delete_trip(repository: Repository, trip_id: str) -> None:
    repository.save_trips([trip for trip in repository.load_trips() if trip.trip_id != trip_id])
    repository.save_route_options([option for option in repository.load_route_options() if option.trip_id != trip_id])
