from __future__ import annotations

from collections import defaultdict
from typing import Callable, TypeVar

from app.models.base import BookingStatus

T = TypeVar("T")


def _snapshot_cache(snapshot: object) -> dict[str, object]:
    cache = getattr(snapshot, "_query_cache", None)
    if cache is None:
        cache = {}
        setattr(snapshot, "_query_cache", cache)
    return cache


def _cached(snapshot: object, key: str, factory: Callable[[], T]) -> T:
    cache = _snapshot_cache(snapshot)
    if key not in cache:
        cache[key] = factory()
    return cache[key]  # type: ignore[return-value]


def trip_map(snapshot) -> dict[str, object]:
    return _cached(
        snapshot,
        "trip_map",
        lambda: {trip.trip_id: trip for trip in snapshot.trips},
    )


def trip_group_map(snapshot) -> dict[str, object]:
    return _cached(
        snapshot,
        "trip_group_map",
        lambda: {group.trip_group_id: group for group in snapshot.trip_groups},
    )


def trip_instance_map(snapshot) -> dict[str, object]:
    return _cached(
        snapshot,
        "trip_instance_map",
        lambda: {instance.trip_instance_id: instance for instance in snapshot.trip_instances},
    )


def route_option_map(snapshot) -> dict[str, object]:
    return _cached(
        snapshot,
        "route_option_map",
        lambda: {option.route_option_id: option for option in snapshot.route_options},
    )


def instances_by_trip(snapshot) -> dict[str, list[object]]:
    def factory() -> dict[str, list[object]]:
        grouped: dict[str, list[object]] = defaultdict(list)
        for instance in snapshot.trip_instances:
            grouped[instance.trip_id].append(instance)
        for items in grouped.values():
            items.sort(key=lambda item: item.anchor_date)
        return dict(grouped)

    return _cached(snapshot, "instances_by_trip", factory)


def instances_by_rule(snapshot) -> dict[str, list[object]]:
    def factory() -> dict[str, list[object]]:
        grouped: dict[str, list[object]] = defaultdict(list)
        for instance in snapshot.trip_instances:
            if instance.recurring_rule_trip_id:
                grouped[instance.recurring_rule_trip_id].append(instance)
        for items in grouped.values():
            items.sort(key=lambda item: item.anchor_date)
        return dict(grouped)

    return _cached(snapshot, "instances_by_rule", factory)


def rule_group_ids_by_rule(snapshot) -> dict[str, list[str]]:
    def factory() -> dict[str, list[str]]:
        grouped: dict[str, set[str]] = defaultdict(set)
        for target in snapshot.rule_group_targets:
            grouped[target.rule_trip_id].add(target.trip_group_id)
        return {
            rule_trip_id: sorted(group_ids)
            for rule_trip_id, group_ids in grouped.items()
        }

    return _cached(snapshot, "rule_group_ids_by_rule", factory)


def group_ids_by_instance(snapshot) -> dict[str, list[str]]:
    def factory() -> dict[str, list[str]]:
        grouped: dict[str, set[str]] = defaultdict(set)
        for membership in snapshot.trip_instance_group_memberships:
            grouped[membership.trip_instance_id].add(membership.trip_group_id)
        return {
            trip_instance_id: sorted(group_ids)
            for trip_instance_id, group_ids in grouped.items()
        }

    return _cached(snapshot, "group_ids_by_instance", factory)


def fetch_targets_by_tracker(snapshot) -> dict[str, list[object]]:
    def factory() -> dict[str, list[object]]:
        grouped: dict[str, list[object]] = defaultdict(list)
        for target in getattr(snapshot, "tracker_fetch_targets", []):
            grouped[target.tracker_id].append(target)
        for items in grouped.values():
            items.sort(key=lambda item: (item.origin_airport, item.destination_airport, item.fetch_target_id))
        return dict(grouped)

    return _cached(snapshot, "fetch_targets_by_tracker", factory)


def trackers_by_instance(snapshot) -> dict[str, list[object]]:
    def factory() -> dict[str, list[object]]:
        grouped: dict[str, list[object]] = defaultdict(list)
        for tracker in snapshot.trackers:
            grouped[tracker.trip_instance_id].append(tracker)
        for items in grouped.values():
            items.sort(key=lambda item: (item.rank, item.travel_date, item.tracker_id))
        return dict(grouped)

    return _cached(snapshot, "trackers_by_instance", factory)


def bookings_by_instance(snapshot) -> dict[str, list[object]]:
    def factory() -> dict[str, list[object]]:
        grouped: dict[str, list[object]] = defaultdict(list)
        for booking in snapshot.bookings:
            grouped[booking.trip_instance_id].append(booking)
        for items in grouped.values():
            items.sort(
                key=lambda item: (
                    item.status != BookingStatus.ACTIVE,
                    -(item.booked_at.timestamp()),
                    item.booking_id,
                ),
            )
        return dict(grouped)

    return _cached(snapshot, "bookings_by_instance", factory)


def active_booking_count_by_instance(snapshot) -> dict[str, int]:
    def factory() -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for booking in snapshot.bookings:
            if booking.status == BookingStatus.ACTIVE:
                counts[booking.trip_instance_id] += 1
        return dict(counts)

    return _cached(snapshot, "active_booking_count_by_instance", factory)


def sorted_trip_groups(snapshot) -> list[object]:
    return _cached(
        snapshot,
        "sorted_trip_groups",
        lambda: sorted(snapshot.trip_groups, key=lambda item: item.label.lower()),
    )
