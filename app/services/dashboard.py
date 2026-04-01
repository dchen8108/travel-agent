from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from app.models.base import FetchTargetStatus
from app.models.booking import Booking
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.services.recommendations import best_tracker_for_instance
from app.services.snapshots import AppSnapshot
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


def load_snapshot(repository: Repository, *, recompute: bool = True) -> AppSnapshot:
    repository.ensure_data_dir()
    if recompute:
        return sync_and_persist(repository)
    return AppSnapshot(
        trips=repository.load_trips(),
        route_options=repository.load_route_options(),
        trip_instances=repository.load_trip_instances(),
        trackers=repository.load_trackers(),
        tracker_fetch_targets=repository.load_tracker_fetch_targets(),
        bookings=repository.load_bookings(),
        unmatched_bookings=repository.load_unmatched_bookings(),
        price_records=repository.load_price_records(),
        app_state=repository.load_app_state(),
    )


def booking_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> Booking | None:
    return next(
        (
            booking
            for booking in snapshot.bookings
            if booking.trip_instance_id == trip_instance_id and booking.status == "active"
        ),
        None,
    )


def trip_by_id(snapshot: AppSnapshot, trip_id: str) -> Trip | None:
    return next((trip for trip in snapshot.trips if trip.trip_id == trip_id), None)


def trip_instance_by_id(snapshot: AppSnapshot, trip_instance_id: str) -> TripInstance | None:
    return next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)


def route_options_for_trip(snapshot: AppSnapshot, trip_id: str) -> list[RouteOption]:
    return sorted(
        [option for option in snapshot.route_options if option.trip_id == trip_id],
        key=lambda item: item.rank,
    )


def instances_for_trip(snapshot: AppSnapshot, trip_id: str) -> list[TripInstance]:
    return sorted(
        [instance for instance in snapshot.trip_instances if instance.trip_id == trip_id],
        key=lambda item: item.anchor_date,
    )


def is_past_instance(instance: TripInstance, *, today: date | None = None) -> bool:
    today = today or date.today()
    return instance.anchor_date < today


def horizon_instances_for_trip(snapshot: AppSnapshot, trip_id: str, *, today: date | None = None) -> list[TripInstance]:
    today = today or date.today()
    return [instance for instance in instances_for_trip(snapshot, trip_id) if not is_past_instance(instance, today=today)]


def past_instances_for_trip(snapshot: AppSnapshot, trip_id: str, *, today: date | None = None) -> list[TripInstance]:
    today = today or date.today()
    return [instance for instance in instances_for_trip(snapshot, trip_id) if is_past_instance(instance, today=today)]


def trackers_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> list[Tracker]:
    return sorted(
        [tracker for tracker in snapshot.trackers if tracker.trip_instance_id == trip_instance_id],
        key=lambda item: (item.rank, item.travel_date),
    )


def best_tracker(snapshot: AppSnapshot, trip_instance_id: str) -> Tracker | None:
    return best_tracker_for_instance(trackers_for_instance(snapshot, trip_instance_id))


def fetch_targets_for_tracker(snapshot: AppSnapshot, tracker_id: str) -> list[TrackerFetchTarget]:
    return sorted(
        [target for target in snapshot.tracker_fetch_targets if target.tracker_id == tracker_id],
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


def booked_tracker(snapshot: AppSnapshot, trip_instance_id: str) -> Tracker | None:
    booking = booking_for_instance(snapshot, trip_instance_id)
    if booking is None or not booking.tracker_id:
        return None
    return next((tracker for tracker in snapshot.trackers if tracker.tracker_id == booking.tracker_id), None)


def comparison_tracker(snapshot: AppSnapshot, trip_instance_id: str) -> Tracker | None:
    tracker = booked_tracker(snapshot, trip_instance_id)
    if tracker is not None and tracker.latest_observed_price is not None:
        return tracker
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


def factual_trip_status_label(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return "Unknown"
    if instance.travel_state == "skipped":
        return "Skipped"
    if booking_for_instance(snapshot, trip_instance_id):
        return "Lower fare found" if rebook_savings(snapshot, trip_instance_id) is not None else "Booked"
    fetch_state = tracker_fetch_state(snapshot, trip_instance_id)
    if fetch_state["has_live_price"] and fetch_state["all_trackers_resolved"]:
        return "Ready to book"
    if fetch_state["all_unavailable"] and fetch_state["all_trackers_resolved"]:
        return "No matching flights"
    if fetch_state["has_failure"]:
        return "Retrying fetch"
    if fetch_state["has_trackers"]:
        return "Fetching prices"
    return "No trackers"


def factual_trip_status_tone(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return "neutral"
    if instance.travel_state == "skipped":
        return "neutral"
    if rebook_savings(snapshot, trip_instance_id) is not None:
        return "success"
    if booking_for_instance(snapshot, trip_instance_id):
        return "neutral"
    fetch_state = tracker_fetch_state(snapshot, trip_instance_id)
    if fetch_state["has_live_price"] and fetch_state["all_trackers_resolved"]:
        return "success"
    if fetch_state["all_unavailable"]:
        return "neutral"
    return "warning"


def factual_trip_status_reason(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return ""
    if instance.travel_state == "skipped":
        return "Skipped. Restore it to resume price checks."
    booking = booking_for_instance(snapshot, trip_instance_id)
    tracker = comparison_tracker(snapshot, trip_instance_id)
    if booking is not None:
        savings = rebook_savings(snapshot, trip_instance_id)
        if savings is not None and tracker is not None and tracker.latest_observed_price is not None:
            return (
                f"Current comparable price is ${tracker.latest_observed_price}, "
                f"${savings} below your booked price of ${booking.booked_price}."
            )
        if tracker is not None and tracker.latest_observed_price is not None:
            return (
                f"Booked at ${booking.booked_price}. Current comparable price is "
                f"${tracker.latest_observed_price}."
            )
        return f"Booked at ${booking.booked_price}. No current comparison price yet."
    tracker = best_tracker(snapshot, trip_instance_id)
    fetch_state = tracker_fetch_state(snapshot, trip_instance_id)
    if tracker is not None and tracker.latest_observed_price is not None and fetch_state["all_trackers_resolved"]:
        if tracker.preference_bias_dollars > 0:
            return (
                f"Best current price is ${tracker.latest_observed_price} on option {tracker.rank}, "
                f"after applying a ${tracker.preference_bias_dollars} preference buffer."
            )
        return f"Best current price is ${tracker.latest_observed_price}."
    if tracker is not None and tracker.latest_observed_price is not None:
        return (
            f"Best current price so far is ${tracker.latest_observed_price}. "
            "Travel Agent is still checking the remaining options."
        )
    if fetch_state["all_unavailable"]:
        return "Google Flights is not returning any matching flights right now."
    if fetch_state["has_failure"]:
        return "A recent Google Flights request failed. Travel Agent will retry automatically."
    if fetch_state["has_trackers"]:
        return "Travel Agent is still fetching current prices for this date."
    return "No trackers are available for this date."


def trip_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> Trip | None:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return None
    return trip_by_id(snapshot, instance.trip_id)


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
    if trip.trip_kind == "weekly":
        params.append(("recurring_trip_id", trip.trip_id))
        anchor = f"recurring-{trip.trip_id}"
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


def standalone_trips(snapshot: AppSnapshot) -> list[Trip]:
    return sorted(
        [trip for trip in snapshot.trips if trip.trip_kind != "weekly"],
        key=lambda item: item.label.lower(),
    )


def scheduled_instances(
    snapshot: AppSnapshot,
    *,
    include_skipped: bool = False,
    recurring_trip_ids: set[str] | None = None,
    today: date | None = None,
) -> list[TripInstance]:
    today = today or date.today()
    items = [item for item in snapshot.trip_instances if not is_past_instance(item, today=today)]
    if not include_skipped:
        items = [item for item in items if item.travel_state != "skipped"]
    if recurring_trip_ids:
        items = [item for item in items if item.trip_id in recurring_trip_ids]
    return sorted(
        items,
        key=lambda item: (item.anchor_date, item.display_label.lower()),
    )


def past_instances(
    snapshot: AppSnapshot,
    *,
    include_skipped: bool = False,
    recurring_trip_ids: set[str] | None = None,
    today: date | None = None,
) -> list[TripInstance]:
    today = today or date.today()
    items = [item for item in snapshot.trip_instances if is_past_instance(item, today=today)]
    if not include_skipped:
        items = [item for item in items if item.travel_state != "skipped"]
    if recurring_trip_ids:
        items = [item for item in items if item.trip_id in recurring_trip_ids]
    return sorted(
        items,
        key=lambda item: (item.anchor_date, item.display_label.lower()),
        reverse=True,
    )
