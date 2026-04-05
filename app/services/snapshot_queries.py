from __future__ import annotations

from datetime import date

from app.models.route_option import RouteOption
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_group import TripGroup
from app.models.trip_instance import TripInstance
from app.services.snapshots import AppSnapshot


def trip_by_id(snapshot: AppSnapshot, trip_id: str) -> Trip | None:
    return next((trip for trip in snapshot.trips if trip.trip_id == trip_id), None)


def trip_group_by_id(snapshot: AppSnapshot, trip_group_id: str) -> TripGroup | None:
    return next((group for group in snapshot.trip_groups if group.trip_group_id == trip_group_id), None)


def trip_instance_by_id(snapshot: AppSnapshot, trip_instance_id: str) -> TripInstance | None:
    return next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)


def groups_for_rule(snapshot: AppSnapshot, trip_or_trip_id: Trip | str | None) -> list[TripGroup]:
    trip = trip_or_trip_id if isinstance(trip_or_trip_id, Trip) else trip_by_id(snapshot, trip_or_trip_id or "")
    if trip is None:
        return []
    group_ids = [
        target.trip_group_id
        for target in snapshot.rule_group_targets
        if target.rule_trip_id == trip.trip_id
    ]
    groups = [
        trip_group_by_id(snapshot, trip_group_id)
        for trip_group_id in sorted(set(group_ids))
    ]
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
    return next((option for option in snapshot.route_options if option.route_option_id == route_option_id), None)


def instances_for_trip(snapshot: AppSnapshot, trip_id: str, *, include_deleted: bool = False) -> list[TripInstance]:
    return sorted(
        [
            instance
            for instance in snapshot.trip_instances
            if instance.trip_id == trip_id and (include_deleted or not instance.deleted)
        ],
        key=lambda item: item.anchor_date,
    )


def instances_for_rule(snapshot: AppSnapshot, rule_trip_id: str, *, include_deleted: bool = False) -> list[TripInstance]:
    return sorted(
        [
            instance
            for instance in snapshot.trip_instances
            if instance.recurring_rule_trip_id == rule_trip_id
            and (include_deleted or not instance.deleted)
        ],
        key=lambda item: item.anchor_date,
    )


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
    tracker_fetch_targets = getattr(snapshot, "tracker_fetch_targets", [])
    return sorted(
        [target for target in tracker_fetch_targets if target.tracker_id == tracker_id],
        key=lambda item: (item.origin_airport, item.destination_airport),
    )


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
    group_ids = [
        membership.trip_group_id
        for membership in snapshot.trip_instance_group_memberships
        if membership.trip_instance_id == trip_instance_id
    ]
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
