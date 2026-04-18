from __future__ import annotations

from datetime import date

from app.models.route_option import RouteOption
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_group import TripGroup
from app.models.trip_instance import TripInstance
from app.services.snapshot_index import (
    fetch_targets_by_tracker as fetch_targets_index,
    group_ids_by_instance,
    instances_by_rule as instances_by_rule_index,
    instances_by_trip as instances_by_trip_index,
    route_option_map,
    rule_group_ids_by_rule,
    trip_group_map,
    trip_instance_map,
    trip_map,
)
from app.services.snapshots import AppSnapshot


def trip_by_id(snapshot: AppSnapshot, trip_id: str) -> Trip | None:
    return trip_map(snapshot).get(trip_id)


def trip_group_by_id(snapshot: AppSnapshot, trip_group_id: str) -> TripGroup | None:
    return trip_group_map(snapshot).get(trip_group_id)


def trip_instance_by_id(snapshot: AppSnapshot, trip_instance_id: str) -> TripInstance | None:
    return trip_instance_map(snapshot).get(trip_instance_id)


def groups_for_rule(snapshot: AppSnapshot, trip_or_trip_id: Trip | str | None) -> list[TripGroup]:
    trip = trip_or_trip_id if isinstance(trip_or_trip_id, Trip) else trip_by_id(snapshot, trip_or_trip_id or "")
    if trip is None:
        return []
    groups = [trip_group_by_id(snapshot, trip_group_id) for trip_group_id in rule_group_ids_by_rule(snapshot).get(trip.trip_id, [])]
    return [group for group in groups if group is not None]


def group_for_rule(snapshot: AppSnapshot, trip_or_trip_id: Trip | str | None) -> TripGroup | None:
    groups = groups_for_rule(snapshot, trip_or_trip_id)
    return groups[0] if groups else None


def groups_for_trip(snapshot: AppSnapshot, trip_or_trip_id: Trip | str | None) -> list[TripGroup]:
    trip = trip_or_trip_id if isinstance(trip_or_trip_id, Trip) else trip_by_id(snapshot, trip_or_trip_id or "")
    if trip is None:
        return []
    if trip.trip_kind == "weekly":
        return groups_for_rule(snapshot, trip)
    trip_instance_ids = {
        instance.trip_instance_id
        for instance in snapshot.trip_instances
        if instance.trip_id == trip.trip_id and not instance.deleted
    }
    group_ids = {
        membership.trip_group_id
        for membership in snapshot.trip_instance_group_memberships
        if membership.trip_instance_id in trip_instance_ids
    }
    groups = [
        trip_group_by_id(snapshot, trip_group_id)
        for trip_group_id in sorted(group_ids)
    ]
    return [group for group in groups if group is not None]


def group_for_trip(snapshot: AppSnapshot, trip_or_trip_id: Trip | str | None) -> TripGroup | None:
    groups = groups_for_trip(snapshot, trip_or_trip_id)
    return groups[0] if groups else None


def route_options_for_trip(snapshot: AppSnapshot, trip_id: str) -> list[RouteOption]:
    return sorted(
        [option for option in snapshot.route_options if option.trip_id == trip_id],
        key=lambda item: item.rank,
    )


def route_option_by_id(snapshot: AppSnapshot, route_option_id: str) -> RouteOption | None:
    return route_option_map(snapshot).get(route_option_id)


def instances_for_trip(snapshot: AppSnapshot, trip_id: str, *, include_deleted: bool = False) -> list[TripInstance]:
    items = instances_by_trip_index(snapshot).get(trip_id, [])
    return items if include_deleted else [instance for instance in items if not instance.deleted]


def instances_for_rule(snapshot: AppSnapshot, rule_trip_id: str, *, include_deleted: bool = False) -> list[TripInstance]:
    items = instances_by_rule_index(snapshot).get(rule_trip_id, [])
    return items if include_deleted else [instance for instance in items if not instance.deleted]


def is_past_instance(instance: TripInstance, *, today: date | None = None) -> bool:
    today = today or date.today()
    return instance.anchor_date < today


def horizon_instances_for_trip(
    snapshot: AppSnapshot,
    trip_id: str,
    *,
    today: date | None = None,
    include_deleted: bool = False,
) -> list[TripInstance]:
    today = today or date.today()
    return [
        instance
        for instance in instances_for_trip(snapshot, trip_id, include_deleted=include_deleted)
        if not is_past_instance(instance, today=today)
    ]


def horizon_instances_for_rule(
    snapshot: AppSnapshot,
    rule_trip_id: str,
    *,
    today: date | None = None,
    include_deleted: bool = False,
) -> list[TripInstance]:
    today = today or date.today()
    return [
        instance
        for instance in instances_for_rule(snapshot, rule_trip_id, include_deleted=include_deleted)
        if not is_past_instance(instance, today=today)
    ]


def past_instances_for_trip(
    snapshot: AppSnapshot,
    trip_id: str,
    *,
    today: date | None = None,
    include_deleted: bool = False,
) -> list[TripInstance]:
    today = today or date.today()
    return [
        instance
        for instance in instances_for_trip(snapshot, trip_id, include_deleted=include_deleted)
        if is_past_instance(instance, today=today)
    ]


def fetch_targets_for_tracker(snapshot: AppSnapshot, tracker_id: str) -> list[TrackerFetchTarget]:
    return fetch_targets_index(snapshot).get(tracker_id, [])


def trip_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> Trip | None:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return None
    return trip_by_id(snapshot, instance.trip_id)


def recurring_rule_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> Trip | None:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None or not instance.recurring_rule_trip_id:
        return None
    return trip_by_id(snapshot, instance.recurring_rule_trip_id)


def groups_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> list[TripGroup]:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return []
    group_ids = group_ids_by_instance(snapshot).get(trip_instance_id, [])
    if not group_ids:
        recurring_rule = recurring_rule_for_instance(snapshot, trip_instance_id)
        if recurring_rule is not None:
            return groups_for_rule(snapshot, recurring_rule)
        return groups_for_trip(snapshot, instance.trip_id)
    groups = [
        trip_group_by_id(snapshot, trip_group_id)
        for trip_group_id in sorted(set(group_ids))
    ]
    return [group for group in groups if group is not None]


def group_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> TripGroup | None:
    groups = groups_for_instance(snapshot, trip_instance_id)
    return groups[0] if groups else None
