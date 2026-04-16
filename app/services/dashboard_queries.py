from __future__ import annotations

from datetime import date

from app.models.trip import Trip
from app.models.trip_group import TripGroup
from app.models.trip_instance import TripInstance
from app.services.scheduled_trip_state import active_booking_count_for_instance
from app.services.snapshot_queries import (
    groups_for_instance,
    is_past_instance,
    recurring_rule_for_instance,
)
from app.services.snapshots import AppSnapshot


UNGROUPED_TRIPS_FILTER_VALUE = "__ungrouped__"


def recurring_trips(snapshot: AppSnapshot) -> list[Trip]:
    return sorted(
        [trip for trip in snapshot.trips if trip.trip_kind == "weekly"],
        key=lambda item: item.label.lower(),
    )


def trip_groups(snapshot: AppSnapshot) -> list[TripGroup]:
    return sorted(snapshot.trip_groups, key=lambda item: item.label.lower())


def _instance_matches_group_filter(
    snapshot: AppSnapshot,
    trip_instance_id: str,
    *,
    trip_group_ids: set[str] | None = None,
    include_ungrouped: bool = False,
) -> bool:
    if not trip_group_ids and not include_ungrouped:
        return True
    instance_groups = groups_for_instance(snapshot, trip_instance_id)
    if trip_group_ids and any(group.trip_group_id in trip_group_ids for group in instance_groups):
        return True
    if include_ungrouped and not instance_groups:
        return True
    return False


def recurring_rules_for_group(snapshot: AppSnapshot, trip_group_id: str) -> list[Trip]:
    rule_trip_ids = {
        target.rule_trip_id
        for target in snapshot.rule_group_targets
        if target.trip_group_id == trip_group_id
    }
    return sorted(
        [
            trip
            for trip in snapshot.trips
            if trip.trip_kind == "weekly" and trip.trip_id in rule_trip_ids
        ],
        key=lambda item: item.label.lower(),
    )


def one_time_trips_for_group(snapshot: AppSnapshot, trip_group_id: str) -> list[Trip]:
    trip_ids = {
        instance.trip_id
        for instance in snapshot.trip_instances
        if not instance.deleted
        and any(group.trip_group_id == trip_group_id for group in groups_for_instance(snapshot, instance.trip_instance_id))
    }
    return sorted(
        [
            trip
            for trip in snapshot.trips
            if trip.trip_kind == "one_time" and trip.trip_id in trip_ids and trip.active
        ],
        key=lambda item: (item.anchor_date or date.max, item.label.lower()),
    )


def standalone_trips(snapshot: AppSnapshot) -> list[Trip]:
    return sorted(
        [trip for trip in snapshot.trips if trip.trip_kind != "weekly"],
        key=lambda item: item.label.lower(),
    )


def deleted_one_time_trips(snapshot: AppSnapshot) -> list[Trip]:
    return sorted(
        [trip for trip in snapshot.trips if trip.trip_kind == "one_time" and not trip.active],
        key=lambda item: item.label.lower(),
    )


def scheduled_instances(
    snapshot: AppSnapshot,
    *,
    trip_group_ids: set[str] | None = None,
    recurring_trip_ids: set[str] | None = None,
    include_ungrouped: bool = False,
    today: date | None = None,
) -> list[TripInstance]:
    today = today or date.today()
    trip_map = {trip.trip_id: trip for trip in snapshot.trips}
    items = [
        item
        for item in snapshot.trip_instances
        if not item.deleted
        and not is_past_instance(item, today=today)
        and not (
            (trip := trip_map.get(item.trip_id)) is not None
            and trip.trip_kind == "one_time"
            and not trip.active
        )
    ]
    if trip_group_ids or include_ungrouped:
        items = [
            item
            for item in items
            if _instance_matches_group_filter(
                snapshot,
                item.trip_instance_id,
                trip_group_ids=trip_group_ids,
                include_ungrouped=include_ungrouped,
            )
        ]
    if recurring_trip_ids:
        items = [
            item
            for item in items
            if (
                (rule := recurring_rule_for_instance(snapshot, item.trip_instance_id)) is not None
                and rule.trip_id in recurring_trip_ids
            )
        ]
    return sorted(
        items,
        key=lambda item: (item.anchor_date, item.display_label.lower()),
    )


def past_instances(
    snapshot: AppSnapshot,
    *,
    trip_group_ids: set[str] | None = None,
    recurring_trip_ids: set[str] | None = None,
    include_ungrouped: bool = False,
    today: date | None = None,
) -> list[TripInstance]:
    today = today or date.today()
    items = [item for item in snapshot.trip_instances if not item.deleted and is_past_instance(item, today=today)]
    if trip_group_ids or include_ungrouped:
        items = [
            item
            for item in items
            if _instance_matches_group_filter(
                snapshot,
                item.trip_instance_id,
                trip_group_ids=trip_group_ids,
                include_ungrouped=include_ungrouped,
            )
        ]
    if recurring_trip_ids:
        items = [
            item
            for item in items
            if (
                (rule := recurring_rule_for_instance(snapshot, item.trip_instance_id)) is not None
                and rule.trip_id in recurring_trip_ids
            )
        ]
    return sorted(
        items,
        key=lambda item: (item.anchor_date, item.display_label.lower()),
        reverse=True,
    )


def scheduled_ledger_view(
    snapshot: AppSnapshot,
    *,
    today: date | None = None,
    selected_trip_group_ids: list[str] | None = None,
    include_booked: bool = True,
) -> dict[str, object]:
    today = today or date.today()
    group_items = trip_groups(snapshot)
    valid_group_ids = {group.trip_group_id for group in group_items}
    include_ungrouped = UNGROUPED_TRIPS_FILTER_VALUE in (selected_trip_group_ids or [])
    selected_ids = [
        trip_group_id
        for trip_group_id in (selected_trip_group_ids or [])
        if trip_group_id in valid_group_ids
    ]
    selected_id_set = set(selected_ids)

    scheduled_items = scheduled_instances(
        snapshot,
        trip_group_ids=selected_id_set or None,
        include_ungrouped=include_ungrouped,
        today=today,
    )
    if not include_booked:
        scheduled_items = [
            instance
            for instance in scheduled_items
            if active_booking_count_for_instance(snapshot, instance.trip_instance_id) == 0
        ]

    total_active_scheduled = len(scheduled_instances(snapshot, today=today))
    total_booked_scheduled = len(
        [
            instance
            for instance in snapshot.trip_instances
            if instance.anchor_date >= today
            and not instance.deleted
            and active_booking_count_for_instance(snapshot, instance.trip_instance_id) > 0
        ]
    )

    return {
        "group_items": group_items,
        "scheduled_items": scheduled_items,
        "selected_trip_group_ids": [*selected_ids, *([UNGROUPED_TRIPS_FILTER_VALUE] if include_ungrouped else [])],
        "include_booked": include_booked,
        "total_active_scheduled": total_active_scheduled,
        "total_booked_scheduled": total_booked_scheduled,
        "group_filter_options": [
            {
                "value": UNGROUPED_TRIPS_FILTER_VALUE,
                "label": "No collection",
                "hideValue": True,
                "keywords": "ungrouped no group without collection",
            },
            *(
                {"value": group.trip_group_id, "label": group.label}
                for group in group_items
            ),
        ],
        "today": today,
    }
