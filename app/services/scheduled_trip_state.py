from __future__ import annotations

from decimal import Decimal

from app.models.base import AppState, BookingStatus, FetchTargetStatus
from app.models.booking import Booking
from app.models.tracker import Tracker
from app.money import format_money, parse_money
from app.services.recommendations import best_tracker_for_instance
from app.services.tracker_refresh_state import tracker_has_fresh_price, tracker_target_display_state
from app.services.snapshot_queries import (
    fetch_targets_for_tracker,
    route_option_by_id,
    trip_instance_by_id,
)
from app.services.snapshots import AppSnapshot


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


def trackers_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> list[Tracker]:
    return sorted(
        [tracker for tracker in snapshot.trackers if tracker.trip_instance_id == trip_instance_id],
        key=lambda item: (item.rank, item.travel_date),
    )


def _snapshot_app_state(snapshot: object) -> AppState:
    return getattr(snapshot, "app_state", AppState())


def best_tracker(snapshot: AppSnapshot, trip_instance_id: str) -> Tracker | None:
    app_state = _snapshot_app_state(snapshot)
    fresh_trackers = [
        tracker
        for tracker in trackers_for_instance(snapshot, trip_instance_id)
        if tracker_has_fresh_price(tracker, app_state)
    ]
    return best_tracker_for_instance(fresh_trackers)


def tracker_option_fetch_state(snapshot: AppSnapshot, tracker: Tracker) -> dict[str, object]:
    app_state = _snapshot_app_state(snapshot)
    targets = fetch_targets_for_tracker(snapshot, tracker.tracker_id)
    display_states = [
        tracker_target_display_state(target, app_state)
        for target in targets
    ]
    statuses = {target.last_fetch_status for target in targets}
    has_live_price = tracker_has_fresh_price(tracker, app_state)
    all_unavailable = bool(display_states) and all(
        state == "unavailable" for state in display_states
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


def _tracker_for_route_option(
    snapshot: AppSnapshot,
    trip_instance_id: str,
    route_option_id: str,
) -> Tracker | None:
    if not route_option_id:
        return None
    return next(
        (
            tracker
            for tracker in trackers_for_instance(snapshot, trip_instance_id)
            if tracker.route_option_id == route_option_id
        ),
        None,
    )


def tracker_effective_price(tracker: Tracker | None) -> Decimal | None:
    if tracker is None:
        return None
    raw_price = parse_money(tracker.latest_observed_price)
    if raw_price is None:
        return None
    return raw_price + parse_money(tracker.preference_bias_dollars or 0)


def booking_effective_price(snapshot: AppSnapshot, booking: Booking | None) -> Decimal | None:
    if booking is None:
        return None
    raw_price = parse_money(booking.booked_price)
    if raw_price is None:
        return None
    matched_tracker = _tracker_for_route_option(snapshot, booking.trip_instance_id, booking.route_option_id)
    if matched_tracker is None:
        return None
    return raw_price + parse_money(matched_tracker.preference_bias_dollars or 0)


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


def rebook_savings(snapshot: AppSnapshot, trip_instance_id: str) -> Decimal | None:
    booking = booking_for_instance(snapshot, trip_instance_id)
    tracker = comparison_tracker(snapshot, trip_instance_id)
    booking_effective = booking_effective_price(snapshot, booking)
    tracker_effective = tracker_effective_price(tracker)
    if (
        booking is None
        or tracker is None
        or booking_effective is None
        or tracker_effective is None
        or tracker_effective >= booking_effective
    ):
        return None
    return booking_effective - tracker_effective


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
    booking = booking_for_instance(snapshot, trip_instance_id)
    active_bookings = bookings_for_instance(snapshot, trip_instance_id, statuses={BookingStatus.ACTIVE})
    active_count = len(active_bookings)
    tracker = comparison_tracker(snapshot, trip_instance_id)
    tracker_effective = tracker_effective_price(tracker)
    booking_effective = booking_effective_price(snapshot, booking)
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
                f"{monitoring_label}. Current best raw alternative is {format_money(tracker.latest_observed_price)}, "
                f"{format_money(savings)} below your booked effective price of {format_money(booking_effective)}."
            )
        if tracker is not None and tracker.latest_observed_price is not None and tracker_effective is not None:
            return (
                f"{monitoring_label}. Booked at {format_money(booking.booked_price)}. "
                f"Current best raw alternative is {format_money(tracker.latest_observed_price)} "
                f"with an effective comparison price of {format_money(tracker_effective)}."
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
