from __future__ import annotations

from datetime import date, timedelta

from app.models.base import TravelState, TripInstanceKind, utcnow
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.services.ids import stable_id


def next_weekday_on_or_after(today: date, weekday_name: str) -> date:
    target = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].index(weekday_name)
    delta = (target - today.weekday()) % 7
    return today + timedelta(days=delta)


def desired_anchor_dates(trip: Trip, *, today: date, future_weeks: int) -> list[date]:
    if not trip.active:
        return []
    if trip.trip_kind == "one_time":
        return [trip.anchor_date] if trip.anchor_date else []
    start = next_weekday_on_or_after(today, trip.anchor_weekday)
    return [start + timedelta(days=7 * offset) for offset in range(future_weeks)]


def instance_kind_for_trip(trip: Trip) -> TripInstanceKind:
    if trip.trip_kind == "weekly":
        return TripInstanceKind.GENERATED
    return TripInstanceKind.STANDALONE


def reconcile_trip_instances(
    trips: list[Trip],
    existing_trip_instances: list[TripInstance],
    *,
    today: date,
    future_weeks: int,
) -> list[TripInstance]:
    existing_by_key = {(item.trip_id, item.anchor_date): item for item in existing_trip_instances}
    desired_keys: set[tuple[str, date]] = set()
    kept: list[TripInstance] = []

    for trip in trips:
        instance_kind = instance_kind_for_trip(trip)
        for anchor_date in desired_anchor_dates(trip, today=today, future_weeks=future_weeks):
            key = (trip.trip_id, anchor_date)
            desired_keys.add(key)
            existing = existing_by_key.get(key)
            display_label = trip.label if instance_kind == TripInstanceKind.STANDALONE else f"{trip.label} ({anchor_date.isoformat()})"
            if existing:
                existing.display_label = display_label
                existing.data_scope = trip.data_scope
                existing.instance_kind = instance_kind
                existing.updated_at = utcnow()
                kept.append(existing)
                continue
            kept.append(
                TripInstance(
                    trip_instance_id=stable_id("inst", trip.trip_id, anchor_date.isoformat()),
                    trip_id=trip.trip_id,
                    display_label=display_label,
                    anchor_date=anchor_date,
                    data_scope=trip.data_scope,
                    instance_kind=instance_kind,
                )
            )

    trip_map = {trip.trip_id: trip for trip in trips}
    for instance in existing_trip_instances:
        if (instance.trip_id, instance.anchor_date) in desired_keys:
            continue
        trip = trip_map.get(instance.trip_id)
        if trip is not None and not trip.active:
            instance.data_scope = trip.data_scope
            instance.instance_kind = instance_kind_for_trip(trip)
            instance.display_label = (
                trip.label
                if instance.instance_kind == TripInstanceKind.STANDALONE
                else f"{trip.label} ({instance.anchor_date.isoformat()})"
            )
            instance.updated_at = utcnow()
            kept.append(instance)
            continue
        if instance.anchor_date < today or instance.travel_state != TravelState.OPEN or instance.booking_id:
            if trip is not None:
                instance.data_scope = trip.data_scope
                instance.instance_kind = instance_kind_for_trip(trip)
                instance.display_label = (
                    trip.label
                    if instance.instance_kind == TripInstanceKind.STANDALONE
                    else f"{trip.label} ({instance.anchor_date.isoformat()})"
                )
                instance.updated_at = utcnow()
            kept.append(instance)
            continue
        if trip is None:
            continue

    kept.sort(key=lambda item: (item.anchor_date, item.display_label))
    return kept
