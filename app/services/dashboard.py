from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from app.money import format_money
from app.models.base import BookingStatus, FetchTargetStatus, TravelState
from app.models.booking import Booking
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_group import TripGroup
from app.models.trip_instance import TripInstance
from app.services.recommendations import best_tracker_for_instance
from app.services.data_scope import filter_snapshot, include_test_data_for_ui
from app.services.snapshots import AppSnapshot
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


def load_snapshot(repository: Repository, *, recompute: bool = True) -> AppSnapshot:
    repository.ensure_data_dir()
    app_state = repository.load_app_state()
    if recompute:
        snapshot = sync_and_persist(repository)
    else:
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


def bookings_for_instance(
    snapshot: AppSnapshot,
    trip_instance_id: str,
    *,
    statuses: set[str] | None = None,
) -> list[Booking]:
    relevant = [
        booking
        for booking in snapshot.bookings
        if booking.trip_instance_id == trip_instance_id
        and (statuses is None or booking.status in statuses)
    ]
    return sorted(
        relevant,
        key=lambda item: (
            item.status != BookingStatus.ACTIVE,
            -(item.booked_at.timestamp()),
            item.booking_id,
        ),
    )


def booking_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> Booking | None:
    active = bookings_for_instance(snapshot, trip_instance_id, statuses={BookingStatus.ACTIVE})
    return active[0] if active else None


def active_booking_count_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> int:
    return len(bookings_for_instance(snapshot, trip_instance_id, statuses={BookingStatus.ACTIVE}))


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


def trackers_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> list[Tracker]:
    return sorted(
        [tracker for tracker in snapshot.trackers if tracker.trip_instance_id == trip_instance_id],
        key=lambda item: (item.rank, item.travel_date),
    )


def best_tracker(snapshot: AppSnapshot, trip_instance_id: str) -> Tracker | None:
    return best_tracker_for_instance(trackers_for_instance(snapshot, trip_instance_id))


def fetch_targets_for_tracker(snapshot: AppSnapshot, tracker_id: str) -> list[TrackerFetchTarget]:
    tracker_fetch_targets = getattr(snapshot, "tracker_fetch_targets", [])
    return sorted(
        [target for target in tracker_fetch_targets if target.tracker_id == tracker_id],
        key=lambda item: (item.origin_airport, item.destination_airport),
    )


def tracker_option_fetch_state(snapshot: AppSnapshot, tracker: Tracker) -> dict[str, object]:
    targets = fetch_targets_for_tracker(snapshot, tracker.tracker_id)
    statuses = {target.last_fetch_status for target in targets}
    has_live_price = tracker.latest_observed_price is not None
    all_unavailable = bool(targets) and statuses.issubset(
        {FetchTargetStatus.NO_RESULTS, FetchTargetStatus.NO_WINDOW_MATCH}
    )
    return {
        "targets": targets,
        "has_live_price": has_live_price,
        "all_unavailable": all_unavailable,
        "has_failure": FetchTargetStatus.FAILED in statuses,
        "is_resolved": has_live_price or all_unavailable,
    }


def tracker_fetch_state(snapshot: AppSnapshot, trip_instance_id: str) -> dict[str, object]:
    trackers = trackers_for_instance(snapshot, trip_instance_id)
    tracker_states = [tracker_option_fetch_state(snapshot, tracker) for tracker in trackers]
    targets = [target for state in tracker_states for target in state["targets"]]
    has_live_price = any(bool(state["has_live_price"]) for state in tracker_states)
    all_unavailable = bool(tracker_states) and all(bool(state["all_unavailable"]) for state in tracker_states)
    all_trackers_resolved = bool(trackers) and all(bool(state["is_resolved"]) for state in tracker_states)
    return {
        "has_trackers": bool(trackers),
        "has_targets": bool(targets),
        "has_live_price": has_live_price,
        "all_trackers_resolved": all_trackers_resolved,
        "has_failure": any(bool(state["has_failure"]) for state in tracker_states),
        "has_pending": any(
            target.last_fetch_status == FetchTargetStatus.PENDING
            for target in targets
        ) or any(not bool(state["is_resolved"]) for state in tracker_states),
        "all_unavailable": all_unavailable,
    }


def comparison_tracker(snapshot: AppSnapshot, trip_instance_id: str) -> Tracker | None:
    return best_tracker(snapshot, trip_instance_id)


def rebook_savings(snapshot: AppSnapshot, trip_instance_id: str) -> int | None:
    booking = booking_for_instance(snapshot, trip_instance_id)
    tracker = comparison_tracker(snapshot, trip_instance_id)
    if (
        booking is None
        or tracker is None
        or tracker.latest_observed_price is None
        or tracker.latest_observed_price >= booking.booked_price
    ):
        return None
    return booking.booked_price - tracker.latest_observed_price


def trip_lifecycle_status_label(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return "Unknown"
    return {
        TravelState.PLANNED: "Planned",
        TravelState.BOOKED: "Booked",
        TravelState.SKIPPED: "Skipped",
    }.get(instance.travel_state, "Unknown")


def trip_lifecycle_status_tone(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return "neutral"
    if instance.travel_state == TravelState.SKIPPED:
        return "neutral"
    if instance.travel_state == TravelState.BOOKED:
        return "success"
    return "warning"


def trip_monitoring_status_label(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return "Unknown"
    if instance.travel_state == TravelState.SKIPPED:
        return "Paused"
    fetch_state = tracker_fetch_state(snapshot, trip_instance_id)
    if fetch_state["has_live_price"] and fetch_state["all_trackers_resolved"]:
        return "Tracking"
    if fetch_state["all_unavailable"] and fetch_state["all_trackers_resolved"]:
        return "No matches"
    if fetch_state["has_trackers"]:
        return "Initializing"
    return "No searches"


def trip_recommended_action(snapshot: AppSnapshot, trip_instance_id: str) -> str | None:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None or instance.travel_state == TravelState.SKIPPED:
        return None
    active_bookings = bookings_for_instance(snapshot, trip_instance_id, statuses={BookingStatus.ACTIVE})
    if active_bookings:
        return "Rebook" if rebook_savings(snapshot, trip_instance_id) is not None else None
    fetch_state = tracker_fetch_state(snapshot, trip_instance_id)
    if instance.travel_state == TravelState.PLANNED and fetch_state["has_live_price"] and fetch_state["all_trackers_resolved"]:
        return "Book"
    return None


def trip_status_detail(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return ""
    if instance.travel_state == TravelState.SKIPPED:
        return "Monitoring is paused for this date. Restore the trip to resume price checks."
    booking = booking_for_instance(snapshot, trip_instance_id)
    active_bookings = bookings_for_instance(snapshot, trip_instance_id, statuses={BookingStatus.ACTIVE})
    active_count = len(active_bookings)
    tracker = comparison_tracker(snapshot, trip_instance_id)
    monitoring_label = trip_monitoring_status_label(snapshot, trip_instance_id)
    if booking is not None:
        savings = rebook_savings(snapshot, trip_instance_id)
        if active_count > 1:
            if savings is not None and tracker is not None and tracker.latest_observed_price is not None:
                return (
                    f"{monitoring_label}. There are {active_count} active bookings linked. "
                    f"The latest booked fare is {format_money(booking.booked_price)}, and the best current trip option is "
                    f"{format_money(tracker.latest_observed_price)}."
                )
            if tracker is not None and tracker.latest_observed_price is not None:
                return (
                    f"{monitoring_label}. There are {active_count} active bookings linked. "
                    f"The latest booked fare is {format_money(booking.booked_price)}. "
                    f"Current best option is {format_money(tracker.latest_observed_price)}."
                )
            return (
                f"{monitoring_label}. There are {active_count} active bookings linked. "
                f"The latest booked fare is {format_money(booking.booked_price)}."
            )
        if savings is not None and tracker is not None and tracker.latest_observed_price is not None:
            return (
                f"{monitoring_label}. Current comparable price is {format_money(tracker.latest_observed_price)}, "
                f"{format_money(savings)} below your booked price of {format_money(booking.booked_price)}."
            )
        if tracker is not None and tracker.latest_observed_price is not None:
            return (
                f"{monitoring_label}. Booked at {format_money(booking.booked_price)}. Current comparable price is "
                f"{format_money(tracker.latest_observed_price)}."
            )
        return f"{monitoring_label}. Booked at {format_money(booking.booked_price)}. No current comparison price yet."
    tracker = best_tracker(snapshot, trip_instance_id)
    fetch_state = tracker_fetch_state(snapshot, trip_instance_id)
    if tracker is not None and tracker.latest_observed_price is not None and fetch_state["all_trackers_resolved"]:
        if tracker.preference_bias_dollars > 0:
            return (
                f"Tracking. Best current price is {format_money(tracker.latest_observed_price)} on option {tracker.rank}, "
                f"after applying a {format_money(tracker.preference_bias_dollars)} preference buffer."
            )
        return f"Tracking. Best current price is {format_money(tracker.latest_observed_price)}."
    if tracker is not None and tracker.latest_observed_price is not None:
        return (
            f"Initializing. Best current price so far is {format_money(tracker.latest_observed_price)}. "
            "Milemark is still checking the remaining options."
        )
    if fetch_state["all_unavailable"]:
        return "No matches. Google Flights is not returning any matching flights right now."
    if fetch_state["has_failure"]:
        return "Initializing. A recent Google Flights request failed. Milemark will retry automatically."
    if fetch_state["has_trackers"]:
        return "Initializing. Milemark is still fetching current prices for this date."
    return "No searches. There are no searches configured for this date."


def factual_trip_status_label(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    return trip_lifecycle_status_label(snapshot, trip_instance_id)


def factual_trip_status_tone(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    return trip_lifecycle_status_tone(snapshot, trip_instance_id)


def factual_trip_status_reason(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    return trip_status_detail(snapshot, trip_instance_id)


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


def trip_focus_url(
    snapshot: AppSnapshot,
    trip_id: str,
    *,
    trip_instance_id: str | None = None,
    show_skipped: bool | None = None,
) -> str:
    trip = next((item for item in snapshot.trips if item.trip_id == trip_id), None)
    if trip is None:
        return "/trips"

    trip_instance = (
        next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)
        if trip_instance_id
        else None
    )
    if show_skipped is None and trip_instance is not None:
        show_skipped = trip_instance.travel_state == "skipped"

    params: list[tuple[str, str]] = []
    anchor = ""
    trip_groups = groups_for_trip(snapshot, trip)
    if len(trip_groups) == 1:
        trip_group = trip_groups[0]
        params.append(("trip_group_id", trip_group.trip_group_id))
        anchor = f"group-{trip_group.trip_group_id}"
    else:
        params.append(("q", trip.label))
    if show_skipped:
        params.append(("show_skipped", "true"))
    if trip_instance_id:
        if not (trip_instance and is_past_instance(trip_instance)):
            anchor = f"scheduled-{trip_instance_id}"

    query = urlencode(params, doseq=True)
    url = "/trips"
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


def archived_one_time_trips(snapshot: AppSnapshot) -> list[Trip]:
    return sorted(
        [trip for trip in snapshot.trips if trip.trip_kind == "one_time" and not trip.active],
        key=lambda item: item.label.lower(),
    )


def scheduled_instances(
    snapshot: AppSnapshot,
    *,
    include_skipped: bool = False,
    trip_group_ids: set[str] | None = None,
    recurring_trip_ids: set[str] | None = None,
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
    if not include_skipped:
        items = [item for item in items if item.travel_state != "skipped"]
    if trip_group_ids:
        items = [
            item
            for item in items
            if any(group.trip_group_id in trip_group_ids for group in groups_for_instance(snapshot, item.trip_instance_id))
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
    include_skipped: bool = False,
    trip_group_ids: set[str] | None = None,
    recurring_trip_ids: set[str] | None = None,
    today: date | None = None,
) -> list[TripInstance]:
    today = today or date.today()
    items = [item for item in snapshot.trip_instances if not item.deleted and is_past_instance(item, today=today)]
    if not include_skipped:
        items = [item for item in items if item.travel_state != "skipped"]
    if trip_group_ids:
        items = [
            item
            for item in items
            if any(group.trip_group_id in trip_group_ids for group in groups_for_instance(snapshot, item.trip_instance_id))
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
