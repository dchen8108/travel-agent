from __future__ import annotations

from datetime import date, timedelta

from app.models.base import TripInstanceInheritanceMode, TripInstanceKind, TripKind, utcnow
from app.models.route_option import RouteOption
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.services.ids import stable_id
from app.services.trips import save_trip
from app.storage.repository import Repository


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


def _display_label_for_trip(trip: Trip, *, anchor_date: date, instance_kind: TripInstanceKind) -> str:
    if instance_kind == TripInstanceKind.STANDALONE:
        return trip.label
    return f"{trip.label} ({anchor_date.isoformat()})"


def _trip_key(*, trip_id: str, anchor_date: date) -> tuple[str, str, date]:
    return ("trip", trip_id, anchor_date)


def _rule_key(*, recurring_rule_trip_id: str, rule_occurrence_date: date) -> tuple[str, str, date]:
    return ("rule", recurring_rule_trip_id, rule_occurrence_date)


def _select_reusable_standalone_instance(
    existing_trip_instances: list[TripInstance],
    *,
    trip_id: str,
    desired_anchor_date: date,
    kept_ids: set[str],
) -> TripInstance | None:
    candidates = [
        item
        for item in existing_trip_instances
        if item.trip_id == trip_id
        and item.instance_kind == TripInstanceKind.STANDALONE
        and not item.deleted
        and item.trip_instance_id not in kept_ids
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            item.booking_id == "",
            item.anchor_date != desired_anchor_date,
            item.inheritance_mode != TripInstanceInheritanceMode.DETACHED,
            item.created_at,
            item.trip_instance_id,
        ),
    )


def _record_existing_keys(
    instance: TripInstance,
    trip_map: dict[str, Trip],
) -> list[tuple[str, str, date]]:
    keys = [_trip_key(trip_id=instance.trip_id, anchor_date=instance.anchor_date)]
    if instance.recurring_rule_trip_id and instance.rule_occurrence_date is not None:
        keys.append(
            _rule_key(
                recurring_rule_trip_id=instance.recurring_rule_trip_id,
                rule_occurrence_date=instance.rule_occurrence_date,
            )
        )
        return keys
    trip = trip_map.get(instance.trip_id)
    if trip is not None and trip.trip_kind == "weekly" and instance.instance_kind == TripInstanceKind.GENERATED:
        keys.append(
            _rule_key(
                recurring_rule_trip_id=trip.trip_id,
                rule_occurrence_date=instance.anchor_date,
            )
        )
    return keys


def reconcile_trip_instances(
    trips: list[Trip],
    existing_trip_instances: list[TripInstance],
    *,
    today: date,
    future_weeks: int,
) -> list[TripInstance]:
    trip_map = {trip.trip_id: trip for trip in trips}
    existing_by_key: dict[tuple[str, str, date], TripInstance] = {}
    for item in existing_trip_instances:
        for key in _record_existing_keys(item, trip_map):
            existing_by_key[key] = item

    kept: list[TripInstance] = []
    kept_ids: set[str] = set()

    for trip in trips:
        instance_kind = instance_kind_for_trip(trip)
        if instance_kind != TripInstanceKind.STANDALONE:
            continue
        for anchor_date in desired_anchor_dates(trip, today=today, future_weeks=future_weeks):
            existing = _select_reusable_standalone_instance(
                existing_trip_instances,
                trip_id=trip.trip_id,
                desired_anchor_date=anchor_date,
                kept_ids=kept_ids,
            )
            display_label = _display_label_for_trip(trip, anchor_date=anchor_date, instance_kind=instance_kind)
            if existing:
                existing.display_label = display_label
                existing.trip_id = trip.trip_id
                existing.anchor_date = anchor_date
                existing.data_scope = trip.data_scope
                existing.instance_kind = instance_kind
                existing.recurring_rule_trip_id = (
                    existing.recurring_rule_trip_id
                    if existing.inheritance_mode == TripInstanceInheritanceMode.DETACHED
                    else ""
                )
                existing.rule_occurrence_date = (
                    existing.rule_occurrence_date
                    if existing.inheritance_mode == TripInstanceInheritanceMode.DETACHED
                    else None
                )
                if existing.inheritance_mode != TripInstanceInheritanceMode.DETACHED:
                    existing.inheritance_mode = TripInstanceInheritanceMode.MANUAL
                existing.updated_at = utcnow()
                if existing.trip_instance_id not in kept_ids:
                    kept.append(existing)
                    kept_ids.add(existing.trip_instance_id)
                continue
            instance = TripInstance(
                trip_instance_id=stable_id("inst", trip.trip_id, anchor_date.isoformat()),
                trip_id=trip.trip_id,
                display_label=display_label,
                anchor_date=anchor_date,
                data_scope=trip.data_scope,
                instance_kind=instance_kind,
                inheritance_mode=TripInstanceInheritanceMode.MANUAL,
            )
            kept.append(instance)
            kept_ids.add(instance.trip_instance_id)

    for trip in trips:
        instance_kind = instance_kind_for_trip(trip)
        if instance_kind != TripInstanceKind.GENERATED:
            continue
        for occurrence_date in desired_anchor_dates(trip, today=today, future_weeks=future_weeks):
            key = _rule_key(recurring_rule_trip_id=trip.trip_id, rule_occurrence_date=occurrence_date)
            existing = existing_by_key.get(key)
            if existing and existing.inheritance_mode == TripInstanceInheritanceMode.DETACHED:
                if existing.trip_instance_id not in kept_ids:
                    kept.append(existing)
                    kept_ids.add(existing.trip_instance_id)
                continue
            display_label = _display_label_for_trip(trip, anchor_date=occurrence_date, instance_kind=instance_kind)
            if existing:
                existing.trip_id = trip.trip_id
                existing.display_label = display_label
                if not existing.deleted:
                    existing.anchor_date = occurrence_date
                existing.data_scope = trip.data_scope
                existing.instance_kind = instance_kind
                existing.recurring_rule_trip_id = trip.trip_id
                existing.rule_occurrence_date = occurrence_date
                existing.inheritance_mode = TripInstanceInheritanceMode.ATTACHED
                existing.updated_at = utcnow()
                if existing.trip_instance_id not in kept_ids:
                    kept.append(existing)
                    kept_ids.add(existing.trip_instance_id)
                continue
            instance = TripInstance(
                trip_instance_id=stable_id("inst", trip.trip_id, occurrence_date.isoformat()),
                trip_id=trip.trip_id,
                display_label=display_label,
                anchor_date=occurrence_date,
                data_scope=trip.data_scope,
                instance_kind=instance_kind,
                recurring_rule_trip_id=trip.trip_id,
                rule_occurrence_date=occurrence_date,
                inheritance_mode=TripInstanceInheritanceMode.ATTACHED,
            )
            kept.append(instance)
            kept_ids.add(instance.trip_instance_id)
    for instance in existing_trip_instances:
        if instance.trip_instance_id in kept_ids:
            continue
        trip = trip_map.get(instance.trip_id)
        rule_trip = trip_map.get(instance.recurring_rule_trip_id) if instance.recurring_rule_trip_id else None
        if instance.deleted:
            if trip is not None:
                instance.data_scope = trip.data_scope
            elif rule_trip is not None:
                instance.data_scope = rule_trip.data_scope
            instance.updated_at = utcnow()
            kept.append(instance)
            continue
        if trip is not None and not trip.active:
            instance.data_scope = trip.data_scope
            instance.instance_kind = instance_kind_for_trip(trip)
            instance.display_label = _display_label_for_trip(
                trip,
                anchor_date=instance.anchor_date,
                instance_kind=instance.instance_kind,
            )
            instance.updated_at = utcnow()
            kept.append(instance)
            continue
        if rule_trip is not None and not rule_trip.active:
            instance.data_scope = rule_trip.data_scope
            instance.updated_at = utcnow()
            kept.append(instance)
            continue
        if instance.anchor_date < today or instance.booking_id:
            if trip is not None:
                instance.data_scope = trip.data_scope
                instance.instance_kind = instance_kind_for_trip(trip)
                instance.display_label = _display_label_for_trip(
                    trip,
                    anchor_date=instance.anchor_date,
                    instance_kind=instance.instance_kind,
                )
                instance.updated_at = utcnow()
            kept.append(instance)
            continue
        if trip is None:
            continue

    kept.sort(key=lambda item: (item.anchor_date, item.display_label))
    return kept


def _route_option_payloads(route_options: list[RouteOption]) -> list[dict[str, object]]:
    return [
        {
            "origin_airports": option.origin_airports,
            "destination_airports": option.destination_airports,
            "airlines": option.airlines,
            "day_offset": option.day_offset,
            "start_time": option.start_time,
            "end_time": option.end_time,
            "fare_class": option.fare_class,
            "savings_needed_vs_previous": option.savings_needed_vs_previous,
        }
        for option in sorted(route_options, key=lambda item: item.rank)
    ]


def detach_generated_trip_instance(repository: Repository, trip_instance_id: str) -> TripInstance:
    with repository.transaction():
        trip_instances = repository.load_trip_instances()
        trip_instance = next((item for item in trip_instances if item.trip_instance_id == trip_instance_id), None)
        if trip_instance is None:
            raise KeyError("Trip instance not found")
        if trip_instance.deleted:
            raise ValueError("Deleted trip instances cannot be detached.")
        if trip_instance.inheritance_mode != TripInstanceInheritanceMode.ATTACHED or not trip_instance.recurring_rule_trip_id:
            raise ValueError("Only attached recurring-rule trips can be detached.")
        trips = repository.load_trips()
        recurring_rule = next((item for item in trips if item.trip_id == trip_instance.recurring_rule_trip_id), None)
        if recurring_rule is None or recurring_rule.trip_kind != TripKind.WEEKLY:
            raise KeyError("Recurring rule not found")

        new_trip = save_trip(
            repository,
            trip_id=None,
            label=trip_instance.display_label,
            trip_kind=TripKind.ONE_TIME,
            active=True,
            anchor_date=trip_instance.anchor_date,
            anchor_weekday="",
            preference_mode=recurring_rule.preference_mode,
            route_option_payloads=_route_option_payloads(
                [option for option in repository.load_route_options() if option.trip_id == recurring_rule.trip_id]
            ),
            data_scope=trip_instance.data_scope,
        )

        trip_instance.trip_id = new_trip.trip_id
        trip_instance.display_label = new_trip.label
        trip_instance.instance_kind = TripInstanceKind.STANDALONE
        trip_instance.inheritance_mode = TripInstanceInheritanceMode.DETACHED
        trip_instance.recurring_rule_trip_id = recurring_rule.trip_id
        trip_instance.rule_occurrence_date = trip_instance.rule_occurrence_date or trip_instance.anchor_date
        trip_instance.updated_at = utcnow()
        repository.upsert_trip_instances([trip_instance])
        return trip_instance


def delete_generated_trip_instance(repository: Repository, trip_instance_id: str) -> TripInstance:
    trip_instances = repository.load_trip_instances()
    trip_instance = next((item for item in trip_instances if item.trip_instance_id == trip_instance_id), None)
    if trip_instance is None:
        raise KeyError("Trip instance not found")
    if trip_instance.inheritance_mode != TripInstanceInheritanceMode.ATTACHED or not trip_instance.recurring_rule_trip_id:
        raise ValueError("Only attached recurring-rule trips can be deleted this way.")
    trip_instance.deleted = True
    trip_instance.updated_at = utcnow()
    repository.upsert_trip_instances([trip_instance])
    return trip_instance


def set_trip_instance_skipped(
    repository: Repository,
    trip_instance_id: str,
    *,
    skipped: bool,
) -> TripInstance:
    trip_instances = repository.load_trip_instances()
    trip_instance = next((item for item in trip_instances if item.trip_instance_id == trip_instance_id), None)
    if trip_instance is None:
        raise KeyError("Trip instance not found")
    if trip_instance.deleted:
        raise ValueError("Deleted trip instances cannot be updated.")
    trip_instance.skipped = skipped
    trip_instance.updated_at = utcnow()
    repository.upsert_trip_instances([trip_instance])
    return trip_instance
