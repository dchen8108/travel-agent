from __future__ import annotations

from datetime import date

from app.models.route_option import RouteOption
from app.models.trip import Trip
from app.models.base import DataScope, FareClassPolicy, RoutePreferenceMode, TripKind, utcnow
from app.route_options import time_windows_overlap
from app.services.group_memberships import build_rule_group_targets
from app.services.ids import new_id
from app.storage.repository import Repository


def parse_trip_kind(raw: str) -> TripKind:
    return TripKind(raw)


def parse_preference_mode(raw: str) -> RoutePreferenceMode:
    return RoutePreferenceMode(raw)


def normalize_trip_label(label: str) -> str:
    return label.strip().lower()


def ensure_valid_trip_label(
    trips: list[Trip],
    label: str,
    *,
    trip_kind: TripKind,
    anchor_date: date | None,
    existing_trip_id: str | None = None,
) -> None:
    normalized = normalize_trip_label(label)
    for trip in trips:
        if existing_trip_id and trip.trip_id == existing_trip_id:
            continue
        if normalize_trip_label(trip.label) != normalized:
            continue

        if trip.trip_kind == TripKind.WEEKLY:
            if trip_kind == TripKind.WEEKLY:
                raise ValueError("Recurring trips must use a unique Trip Label.")
            raise ValueError("This Trip Label is already used by a recurring trip.")

        if trip_kind == TripKind.WEEKLY:
            raise ValueError("Recurring trips must use a unique Trip Label.")

        if trip.active and trip.anchor_date == anchor_date:
            raise ValueError("A one-time trip with this Trip Label and date already exists.")


def build_trip(
    *,
    trip_id: str | None,
    label: str,
    trip_kind: str,
    active: bool,
    anchor_date: date | None,
    anchor_weekday: str,
    preference_mode: str = RoutePreferenceMode.EQUAL,
    data_scope: str = DataScope.LIVE,
) -> Trip:
    now = utcnow()
    return Trip(
        trip_id=trip_id or new_id("trip"),
        label=label,
        trip_kind=parse_trip_kind(trip_kind),
        preference_mode=parse_preference_mode(preference_mode),
        data_scope=DataScope(data_scope),
        active=active,
        anchor_date=anchor_date,
        anchor_weekday=anchor_weekday,
        created_at=now,
        updated_at=now,
    )


def _route_options_overlap(left: RouteOption, right: RouteOption) -> bool:
    if left.day_offset != right.day_offset:
        return False
    if not set(left.origin_codes) & set(right.origin_codes):
        return False
    if not set(left.destination_codes) & set(right.destination_codes):
        return False
    if not set(left.airline_codes) & set(right.airline_codes):
        return False
    return time_windows_overlap(left.start_time, left.end_time, right.start_time, right.end_time)


def build_route_options(
    *,
    trip_id: str,
    data_scope: str,
    payloads: list[dict[str, object]],
    existing_route_options: list[RouteOption] | None = None,
) -> list[RouteOption]:
    existing_by_id = {option.route_option_id: option for option in existing_route_options or []}
    built: list[RouteOption] = []
    seen_signatures: set[tuple[str, str, str, int, str, str, str]] = set()
    for index, payload in enumerate(payloads, start=1):
        route_option_id = str(payload.get("route_option_id") or "").strip() or new_id("opt")
        original = existing_by_id.get(route_option_id)
        option = RouteOption(
            route_option_id=route_option_id,
            trip_id=trip_id,
            rank=index,
            data_scope=DataScope(data_scope),
            savings_needed_vs_previous=0 if index == 1 else int(payload.get("savings_needed_vs_previous", 0)),
            origin_airports=str(payload.get("origin_airports", "")),
            destination_airports=str(payload.get("destination_airports", "")),
            airlines=str(payload.get("airlines", "")),
            day_offset=int(payload.get("day_offset", 0)),
            start_time=str(payload.get("start_time", "")),
            end_time=str(payload.get("end_time", "")),
            fare_class_policy=FareClassPolicy(str(payload.get("fare_class_policy", FareClassPolicy.INCLUDE_BASIC))),
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
            option.fare_class_policy,
        )
        if signature in seen_signatures:
            raise ValueError("Duplicate route options are not allowed.")
        seen_signatures.add(signature)
        for existing in built:
            if _route_options_overlap(existing, option):
                raise ValueError(
                    f"Route options {existing.rank} and {option.rank} overlap. "
                    "Each booking on a trip must match at most one route option."
                )
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
    trip_group_ids: list[str] | None = None,
    route_option_payloads: list[dict[str, object]],
    preference_mode: str = RoutePreferenceMode.EQUAL,
    data_scope: str = DataScope.LIVE,
) -> Trip:
    trips = repository.load_trips()
    route_options = repository.load_route_options()
    parsed_trip_kind = parse_trip_kind(trip_kind)
    ensure_valid_trip_label(
        trips,
        label,
        trip_kind=parsed_trip_kind,
        anchor_date=anchor_date,
        existing_trip_id=trip_id,
    )

    existing_trip = next((trip for trip in trips if trip.trip_id == trip_id), None) if trip_id else None
    if trip_id and existing_trip is None:
        raise ValueError("Trip not found.")
    trip = build_trip(
        trip_id=trip_id,
        label=label,
        trip_kind=parsed_trip_kind,
        preference_mode=preference_mode,
        data_scope=data_scope,
        active=active,
        anchor_date=anchor_date,
        anchor_weekday=anchor_weekday,
    )
    if existing_trip:
        trip.created_at = existing_trip.created_at
        trip.updated_at = utcnow()
        if not data_scope:
            trip.data_scope = existing_trip.data_scope

    existing_route_options = [option for option in route_options if option.trip_id == trip.trip_id]
    built_route_options = build_route_options(
        trip_id=trip.trip_id,
        data_scope=trip.data_scope,
        payloads=route_option_payloads,
        existing_route_options=existing_route_options,
    )
    existing_rule_targets = repository.load_rule_group_targets()
    next_trip_group_ids = sorted(
        {
            trip_group
            for trip_group in (trip_group_ids or [])
            if trip_group
        }
    )
    next_rule_targets = build_rule_group_targets(
        rule_trip_id=trip.trip_id,
        trip_group_ids=next_trip_group_ids if parsed_trip_kind == TripKind.WEEKLY else [],
        data_scope=trip.data_scope,
        existing_targets=[target for target in existing_rule_targets if target.rule_trip_id == trip.trip_id],
    )

    with repository.transaction():
        repository.upsert_trip(trip)
        repository.replace_route_options_for_trip(trip.trip_id, built_route_options)
        repository.replace_rule_group_targets_for_rule(trip.trip_id, next_rule_targets)
    return trip


def save_past_trip(
    repository: Repository,
    *,
    trip_id: str | None,
    label: str,
    anchor_date: date,
) -> Trip:
    trips = repository.load_trips()
    ensure_valid_trip_label(
        trips,
        label,
        trip_kind=TripKind.ONE_TIME,
        anchor_date=anchor_date,
        existing_trip_id=trip_id,
    )

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

    with repository.transaction():
        repository.upsert_trip(trip)
    return trip


def set_trip_active(repository: Repository, trip_id: str, active: bool) -> Trip:
    trips = repository.load_trips()
    trip = next((item for item in trips if item.trip_id == trip_id), None)
    if trip is None:
        raise KeyError("Trip not found")
    trip.active = active
    trip.updated_at = utcnow()
    repository.upsert_trip(trip)
    return trip


def delete_trip(repository: Repository, trip_id: str) -> None:
    trips = repository.load_trips()
    trip = next((item for item in trips if item.trip_id == trip_id), None)
    if trip is None:
        raise KeyError("Trip not found")
    if trip.trip_kind != TripKind.ONE_TIME:
        raise ValueError("Only one-time trips can be deleted.")
    trip.active = False
    trip.updated_at = utcnow()
    repository.upsert_trip(trip)
