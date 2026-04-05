from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from app.models.base import BookingStatus
from app.models.booking import Booking
from app.models.trip import Trip
from app.models.trip_group import TripGroup
from app.models.trip_instance import TripInstance
from app.route_options import split_pipe
from app.services.scheduled_trip_views import (
    active_booking_count_for_instance,
)
from app.services.snapshot_queries import (
    group_for_rule,
    group_for_trip,
    groups_for_instance,
    groups_for_rule,
    groups_for_trip,
    horizon_instances_for_rule,
    horizon_instances_for_trip,
    instances_for_rule,
    instances_for_trip,
    is_past_instance,
    past_instances_for_trip,
    recurring_rule_for_instance,
    route_options_for_trip,
    trip_by_id,
    trip_for_instance,
    trip_group_by_id,
)
from app.services.data_scope import filter_snapshot, include_test_data_for_ui
from app.services.snapshots import AppSnapshot
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


def load_persisted_snapshot(repository: Repository) -> AppSnapshot:
    repository.ensure_data_dir()
    app_state = repository.load_app_state()
    snapshot = AppSnapshot(
        trip_groups=repository.load_trip_groups(),
        trips=repository.load_trips(),
        rule_group_targets=repository.load_rule_group_targets(),
        route_options=repository.load_route_options(),
        trip_instances=repository.load_trip_instances(),
        trip_instance_group_memberships=repository.load_trip_instance_group_memberships(),
        trackers=repository.load_trackers(),
        tracker_fetch_targets=repository.load_tracker_fetch_targets(),
        bookings=repository.load_bookings(),
        unmatched_bookings=repository.load_unmatched_bookings(),
        booking_email_events=repository.load_booking_email_events(),
        price_records=repository.load_price_records(),
        app_state=app_state,
    )
    return filter_snapshot(snapshot, include_test_data=include_test_data_for_ui(app_state))


def load_live_snapshot(repository: Repository, *, today: date | None = None) -> AppSnapshot:
    repository.ensure_data_dir()
    snapshot = sync_and_persist(repository, today=today)
    return filter_snapshot(snapshot, include_test_data=include_test_data_for_ui(snapshot.app_state))


def booking_reference_label(booking: Booking) -> str:
    return f"Booking {booking.record_locator}" if booking.record_locator else "Imported booking"


def default_trip_label_for_booking(booking: Booking) -> str:
    if booking.origin_airport and booking.destination_airport:
        return f"{booking.origin_airport} to {booking.destination_airport}"
    return booking_reference_label(booking)


def trip_focus_url(
    snapshot: AppSnapshot,
    trip_id: str,
    *,
    trip_instance_id: str | None = None,
) -> str:
    trip = next((item for item in snapshot.trips if item.trip_id == trip_id), None)
    if trip is None:
        return "/#all-travel"

    params: list[tuple[str, str]] = []
    anchor = ""
    trip_groups = groups_for_trip(snapshot, trip)
    if len(trip_groups) == 1:
        trip_group = trip_groups[0]
        params.append(("trip_group_id", trip_group.trip_group_id))
        anchor = f"group-{trip_group.trip_group_id}"
    else:
        params.append(("q", trip.label))
    if trip_instance_id:
        trip_instance = next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)
        if not (trip_instance and is_past_instance(trip_instance)):
            anchor = f"scheduled-{trip_instance_id}"

    query = urlencode(params, doseq=True)
    url = "/"
    if query:
        url = f"{url}?{query}"
    if anchor:
        url = f"{url}#{anchor}"
    return url


def tracker_detail_url(trip_instance_id: str) -> str:
    return f"/trip-instances/{trip_instance_id}"


def recurring_trips(snapshot: AppSnapshot) -> list[Trip]:
    return sorted(
        [trip for trip in snapshot.trips if trip.trip_kind == "weekly"],
        key=lambda item: item.label.lower(),
    )


def trip_groups(snapshot: AppSnapshot) -> list[TripGroup]:
    return sorted(snapshot.trip_groups, key=lambda item: item.label.lower())


def selectable_trip_instances_for_booking_link(snapshot: AppSnapshot) -> list[TripInstance]:
    return sorted(
        [
            item
            for item in snapshot.trip_instances
            if not item.deleted and (
                (parent_trip := trip_for_instance(snapshot, item.trip_instance_id)) is None
                or parent_trip.trip_kind != "one_time"
                or parent_trip.active
            )
        ],
        key=lambda item: (
            item.anchor_date,
            item.display_label.lower(),
        ),
    )


def unmatched_booking_resolution_views(snapshot: AppSnapshot) -> list[dict[str, object]]:
    selectable_trip_instances = selectable_trip_instances_for_booking_link(snapshot)
    trip_instances_by_id = {item.trip_instance_id: item for item in selectable_trip_instances}
    today = date.today()
    cards: list[dict[str, object]] = []
    for unmatched in sorted(
        [
            item
            for item in snapshot.unmatched_bookings
            if item.status == BookingStatus.ACTIVE and item.needs_linking
        ],
        key=lambda item: (item.departure_date, item.departure_time, item.record_locator),
    ):
        candidate_ids = [
            item for item in split_pipe(unmatched.candidate_trip_instance_ids) if item in trip_instances_by_id
        ]
        suggested_trip_instances = [trip_instances_by_id[item] for item in candidate_ids]
        suggested_ids = {item.trip_instance_id for item in suggested_trip_instances}
        other_trip_instances = [
            item for item in selectable_trip_instances if item.trip_instance_id not in suggested_ids
        ]
        upcoming_trip_instances = [
            item for item in other_trip_instances if item.anchor_date >= today
        ]
        past_trip_instances = [
            item for item in other_trip_instances if item.anchor_date < today
        ]
        cards.append(
            {
                "unmatched": unmatched,
                "booking_reference_label": booking_reference_label(unmatched),
                "suggested_trip_label": default_trip_label_for_booking(unmatched),
                "suggested_trip_instances": suggested_trip_instances,
                "upcoming_trip_instances": upcoming_trip_instances,
                "past_trip_instances": past_trip_instances,
            }
        )
    return cards


def scheduled_ledger_view(
    snapshot: AppSnapshot,
    *,
    today: date | None = None,
    selected_trip_group_ids: list[str] | None = None,
    search_query: str = "",
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
    query = search_query.strip()
    if query:
        lowered = query.lower()
        scheduled_items = [
            instance
            for instance in scheduled_items
            if lowered in instance.display_label.lower()
            or (
                (parent_trip := trip_for_instance(snapshot, instance.trip_instance_id)) is not None
                and lowered in parent_trip.label.lower()
            )
            or any(
                lowered in trip_group.label.lower()
                for trip_group in groups_for_instance(snapshot, instance.trip_instance_id)
            )
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
        "search_query": query,
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


UNGROUPED_TRIPS_FILTER_VALUE = "__ungrouped__"


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
