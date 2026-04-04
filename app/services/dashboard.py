from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlencode

from app.catalog import airline_display
from app.money import format_money
from app.models.base import BookingStatus, FetchTargetStatus
from app.models.booking import Booking
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_group import TripGroup
from app.models.trip_instance import TripInstance
from app.route_options import split_pipe
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


def booking_reference_label(booking: Booking) -> str:
    return f"Booking {booking.record_locator}" if booking.record_locator else "Imported booking"


def default_trip_label_for_booking(booking: Booking) -> str:
    if booking.origin_airport and booking.destination_airport:
        return f"{booking.origin_airport} to {booking.destination_airport}"
    return booking_reference_label(booking)


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


def booking_route_tracking_state(snapshot: AppSnapshot, booking: Booking) -> dict[str, object]:
    trip_instance = trip_instance_by_id(snapshot, booking.trip_instance_id)
    if trip_instance is None:
        return {
            "route_option": None,
            "summary_label": "—",
            "warning": "",
        }
    trackers = trackers_for_instance(snapshot, booking.trip_instance_id)
    matched_route_option = route_option_by_id(snapshot, booking.route_option_id) if booking.route_option_id else None
    if matched_route_option is not None:
        return {
            "route_option": matched_route_option,
            "summary_label": f"Matches option {matched_route_option.rank}",
            "warning": "",
        }
    if trackers:
        return {
            "route_option": None,
            "summary_label": "No tracked route match",
            "warning": "This booking is linked to the trip, but it does not match any tracked route on this date yet.",
        }
    return {
        "route_option": None,
        "summary_label": "No tracked routes",
        "warning": "This trip does not have any tracked routes yet, so Milemark cannot monitor this exact itinerary.",
    }


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


def trip_lifecycle_status_key(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return "unknown"
    if active_booking_count_for_instance(snapshot, trip_instance_id) > 0:
        return "booked"
    return "planned"


def trip_lifecycle_status_label(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    return {
        "planned": "Planned",
        "booked": "Booked",
    }.get(trip_lifecycle_status_key(snapshot, trip_instance_id), "Unknown")


def trip_lifecycle_status_tone(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    lifecycle = trip_lifecycle_status_key(snapshot, trip_instance_id)
    if lifecycle == "booked":
        return "success"
    if lifecycle == "planned":
        return "warning"
    return "neutral"


def trip_monitoring_status_label(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return "Unknown"
    fetch_state = tracker_fetch_state(snapshot, trip_instance_id)
    if fetch_state["has_live_price"] and fetch_state["all_trackers_resolved"]:
        return "Tracking"
    if fetch_state["all_unavailable"] and fetch_state["all_trackers_resolved"]:
        return "No matches"
    return "Initializing"


def trip_recommended_action(snapshot: AppSnapshot, trip_instance_id: str) -> str | None:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return None
    active_bookings = bookings_for_instance(snapshot, trip_instance_id, statuses={BookingStatus.ACTIVE})
    if active_bookings:
        return "Rebook" if rebook_savings(snapshot, trip_instance_id) is not None else None
    fetch_state = tracker_fetch_state(snapshot, trip_instance_id)
    if fetch_state["has_live_price"] and fetch_state["all_trackers_resolved"]:
        return "Book"
    return None


def trip_status_detail(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return ""
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
    return "Initializing. Milemark is still preparing this date for price tracking."


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


def trip_ui_label(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    group = group_for_instance(snapshot, trip_instance_id)
    if group is not None:
        return group.label
    trip = trip_for_instance(snapshot, trip_instance_id)
    if trip is not None:
        return trip.label
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    return instance.display_label if instance is not None else ""


def trip_ui_context_label(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    title = trip_ui_label(snapshot, trip_instance_id)
    trip = trip_for_instance(snapshot, trip_instance_id)
    if group_for_instance(snapshot, trip_instance_id) is not None:
        if trip is not None and trip.label and trip.label != title:
            return trip.label
        return ""
    recurring_rule = recurring_rule_for_instance(snapshot, trip_instance_id)
    if recurring_rule is not None and (trip is None or recurring_rule.trip_id != trip.trip_id):
        return recurring_rule.label
    return ""


def _compact_airport_codes(codes: list[str]) -> str:
    return "|".join(code for code in codes if code)


def _row_tracker(snapshot: AppSnapshot, trip_instance_id: str) -> Tracker | None:
    tracker = comparison_tracker(snapshot, trip_instance_id)
    if tracker is not None:
        return tracker
    trackers = trackers_for_instance(snapshot, trip_instance_id)
    return trackers[0] if trackers else None


def _tracker_route_label(tracker: Tracker) -> str:
    if tracker.latest_winning_origin_airport and tracker.latest_winning_destination_airport:
        return f"{tracker.latest_winning_origin_airport} → {tracker.latest_winning_destination_airport}"
    origins = _compact_airport_codes(tracker.origin_codes)
    destinations = _compact_airport_codes(tracker.destination_codes)
    if origins and destinations:
        return f"{origins} → {destinations}"
    return ""


def _booking_route_label(booking: Booking) -> str:
    route = f"{booking.origin_airport} → {booking.destination_airport}"
    airline = airline_display(booking.airline)
    return f"{route} · {airline}" if airline else route


def _format_departure_time_label(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    if "am" in raw.lower() or "pm" in raw.lower():
        return raw
    try:
        parsed = datetime.strptime(raw, "%H:%M")
    except ValueError:
        return raw
    return parsed.strftime("%I:%M %p").lstrip("0")


def _travel_day_delta_label(anchor_date: date, travel_date: date | None) -> str:
    if travel_date is None:
        return ""
    delta = (travel_date - anchor_date).days
    if delta == 0:
        return ""
    unit = "day" if abs(delta) == 1 else "days"
    return f"{delta:+d} {unit}"


def _tracker_display_label(
    tracker: Tracker | None,
    *,
    current_target: TrackerFetchTarget | None = None,
) -> str:
    if current_target is not None:
        return _fetch_target_route_label(current_target, fallback_tracker=tracker)
    if tracker is None:
        return ""
    route = _tracker_route_label(tracker)
    if not route:
        return ""
    if len(tracker.airline_codes) == 1:
        return f"{route} · {airline_display(tracker.airline_codes[0])}"
    return route


def _fetch_target_route_label(
    target: TrackerFetchTarget,
    *,
    fallback_tracker: Tracker | None = None,
) -> str:
    route = f"{target.origin_airport} → {target.destination_airport}"
    airline = airline_display(target.latest_airline) if target.latest_airline else ""
    if not airline and fallback_tracker is not None and len(fallback_tracker.airline_codes) == 1:
        airline = airline_display(fallback_tracker.airline_codes[0])
    return f"{route} · {airline}" if airline else route


def tracker_best_fetch_target(snapshot: AppSnapshot, tracker: Tracker | None) -> TrackerFetchTarget | None:
    if tracker is None:
        return None
    targets = fetch_targets_for_tracker(snapshot, tracker.tracker_id)
    if not targets:
        return None
    if tracker.latest_winning_origin_airport and tracker.latest_winning_destination_airport:
        exact_targets = [
            target
            for target in targets
            if target.origin_airport == tracker.latest_winning_origin_airport
            and target.destination_airport == tracker.latest_winning_destination_airport
        ]
        if tracker.latest_observed_price is not None:
            exact_price_match = [
                target
                for target in exact_targets
                if target.latest_price == tracker.latest_observed_price
            ]
            if exact_price_match:
                return sorted(
                    exact_price_match,
                    key=lambda item: (item.origin_airport, item.destination_airport),
                )[0]
        if exact_targets:
            return sorted(
                exact_targets,
                key=lambda item: (item.origin_airport, item.destination_airport),
            )[0]
    if tracker.latest_observed_price is not None:
        priced_targets = [
            target
            for target in targets
            if target.latest_price == tracker.latest_observed_price
        ]
        if priced_targets:
            return sorted(
                priced_targets,
                key=lambda item: (item.origin_airport, item.destination_airport),
            )[0]
    live_targets = [target for target in targets if target.latest_price is not None]
    if live_targets:
        return sorted(
            live_targets,
            key=lambda item: (
                item.latest_price or 10**9,
                item.origin_airport,
                item.destination_airport,
            ),
        )[0]
    return sorted(
        targets,
        key=lambda item: (item.origin_airport, item.destination_airport),
    )[0]


def trip_row_summary(snapshot: AppSnapshot, trip_instance_id: str) -> dict[str, object]:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    booking = booking_for_instance(snapshot, trip_instance_id)
    tracker = comparison_tracker(snapshot, trip_instance_id)
    display_tracker = _row_tracker(snapshot, trip_instance_id)
    active_booking_count = active_booking_count_for_instance(snapshot, trip_instance_id)
    savings = rebook_savings(snapshot, trip_instance_id)
    monitoring_label = trip_monitoring_status_label(snapshot, trip_instance_id)
    current_target = tracker_best_fetch_target(snapshot, display_tracker)
    current_price = tracker.latest_observed_price if tracker is not None else None

    current_offer: dict[str, object] | None = None
    current_offer_label = "Current best"
    current_offer_price = ""
    current_offer_href = ""
    current_offer_tone = "success" if booking is None else "accent"
    if current_price is not None:
        current_offer_price = format_money(current_price)
        current_offer_href = current_target.google_flights_url if current_target and current_target.google_flights_url else ""
    else:
        current_offer_label = "Watching"
        current_offer_price = "No fares" if monitoring_label == "No matches" else "Checking"
        current_offer_tone = "warning" if monitoring_label == "No matches" else "neutral"

    current_offer_detail = _tracker_display_label(display_tracker, current_target=current_target if current_price is not None else None)
    if current_offer_detail or current_offer_price:
        current_offer = {
            "label": current_offer_label,
            "detail": current_offer_detail,
            "meta_label": _format_departure_time_label(current_target.latest_departure_label) if current_target else "",
            "day_delta_label": _travel_day_delta_label(
                instance.anchor_date if instance is not None else date.today(),
                display_tracker.travel_date if display_tracker is not None else None,
            ),
            "price_label": current_offer_price,
            "href": current_offer_href,
            "tone": current_offer_tone,
        }

    booked_offer: dict[str, object] | None = None
    if booking is not None:
        booked_offer = {
            "label": "Latest booked" if active_booking_count > 1 else "Booked",
            "detail": _booking_route_label(booking),
            "meta_label": _format_departure_time_label(booking.departure_time),
            "day_delta_label": _travel_day_delta_label(
                instance.anchor_date if instance is not None else date.today(),
                booking.departure_date,
            ),
            "price_label": format_money(booking.booked_price),
            "href": "",
            "tone": "neutral",
        }

    state_chips: list[dict[str, object]] = []
    if savings is not None:
        state_chips.append(
            {
                "label": f"Save {format_money(savings)}",
                "tone": "accent",
            }
        )
    if active_booking_count > 1:
        state_chips.append(
            {
                "label": f"{active_booking_count} bookings",
                "tone": "warning",
            }
        )

    return {
        "title": trip_ui_label(snapshot, trip_instance_id),
        "lifecycle_label": trip_lifecycle_status_label(snapshot, trip_instance_id),
        "lifecycle_tone": trip_lifecycle_status_tone(snapshot, trip_instance_id),
        "booked_offer": booked_offer,
        "current_offer": current_offer,
        "state_chips": state_chips,
        "has_dual_offers": booked_offer is not None and current_offer is not None,
    }


def trip_ui_picker_label(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return ""
    label = trip_ui_label(snapshot, trip_instance_id)
    return f"{label} · {instance.anchor_date.strftime('%a, %b %d')}"


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
