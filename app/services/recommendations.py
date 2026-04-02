from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from app.models.base import TravelState, utcnow
from app.models.booking import Booking
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip_instance import TripInstance


def apply_fetch_target_rollups(
    trackers: list[Tracker],
    fetch_targets: list[TrackerFetchTarget],
) -> list[Tracker]:
    fresh_window = timedelta(hours=72)
    freshness_cutoff = utcnow() - fresh_window
    by_tracker: dict[str, list[TrackerFetchTarget]] = defaultdict(list)
    for target in fetch_targets:
        if target.latest_price is None or target.latest_fetched_at is None:
            continue
        by_tracker[target.tracker_id].append(target)

    for tracker in trackers:
        candidates = by_tracker.get(tracker.tracker_id, [])
        if not candidates:
            if tracker.latest_signal_source == "background_fetch":
                tracker.latest_observed_price = None
                tracker.last_signal_at = None
                tracker.latest_fetched_at = None
                tracker.latest_winning_origin_airport = ""
                tracker.latest_winning_destination_airport = ""
                tracker.latest_signal_source = ""
                tracker.latest_match_summary = ""
                tracker.updated_at = utcnow()
            continue
        freshest_candidates = [
            target
            for target in candidates
            if target.latest_fetched_at is not None and target.latest_fetched_at >= freshness_cutoff
        ]
        if not freshest_candidates:
            if tracker.latest_signal_source == "background_fetch":
                tracker.latest_observed_price = None
                tracker.last_signal_at = None
                tracker.latest_fetched_at = None
                tracker.latest_winning_origin_airport = ""
                tracker.latest_winning_destination_airport = ""
                tracker.latest_signal_source = ""
                tracker.latest_match_summary = ""
                tracker.updated_at = utcnow()
            continue
        winner = min(
            freshest_candidates,
            key=lambda item: (
                item.latest_price or 10**9,
                item.origin_airport,
                item.destination_airport,
                item.latest_airline,
            ),
        )
        if tracker.last_signal_at and winner.latest_fetched_at and tracker.last_signal_at > winner.latest_fetched_at:
            continue
        tracker.latest_observed_price = winner.latest_price
        tracker.last_signal_at = winner.latest_fetched_at
        tracker.latest_fetched_at = winner.latest_fetched_at
        tracker.latest_winning_origin_airport = winner.origin_airport
        tracker.latest_winning_destination_airport = winner.destination_airport
        tracker.latest_match_summary = (
            winner.latest_summary
            or f"Fetched via {winner.origin_airport} → {winner.destination_airport}"
        )
        tracker.latest_signal_source = "background_fetch"
        tracker.updated_at = utcnow()
    return trackers


def best_tracker_for_instance(trackers: list[Tracker]) -> Tracker | None:
    with_prices = [tracker for tracker in trackers if tracker.latest_observed_price is not None]
    if not with_prices:
        return None
    return min(
        with_prices,
        key=lambda item: (
            (item.latest_observed_price or 10**9) + item.preference_bias_dollars,
            item.latest_observed_price or 10**9,
            item.rank,
        ),
    )


def recompute_trip_states(
    trip_instances: list[TripInstance],
    trackers: list[Tracker],
    bookings: list[Booking],
) -> list[TripInstance]:
    trackers_by_instance: dict[str, list[Tracker]] = defaultdict(list)
    active_bookings_by_instance: dict[str, list[Booking]] = defaultdict(list)

    for tracker in trackers:
        trackers_by_instance[tracker.trip_instance_id].append(tracker)
    for booking in bookings:
        if booking.status == "active":
            active_bookings_by_instance[booking.trip_instance_id].append(booking)

    for instance in trip_instances:
        related_trackers = sorted(trackers_by_instance.get(instance.trip_instance_id, []), key=lambda item: item.rank)
        active_bookings = sorted(
            active_bookings_by_instance.get(instance.trip_instance_id, []),
            key=lambda item: (item.booked_at, item.created_at, item.booking_id),
            reverse=True,
        )
        booking = active_bookings[0] if active_bookings else None
        is_past = instance.anchor_date < date.today()
        instance.last_signal_at = max(
            (tracker.last_signal_at for tracker in related_trackers if tracker.last_signal_at),
            default=None,
        )

        if booking and instance.travel_state != TravelState.SKIPPED:
            instance.travel_state = TravelState.BOOKED
            instance.booking_id = booking.booking_id
        elif instance.travel_state != TravelState.SKIPPED:
            instance.travel_state = TravelState.OPEN
            instance.booking_id = ""

        if instance.travel_state == TravelState.SKIPPED:
            instance.updated_at = utcnow()
            continue

        if booking:
            instance.updated_at = utcnow()
            continue

        if is_past:
            instance.updated_at = utcnow()
            continue

        instance.updated_at = utcnow()

    trip_instances.sort(key=lambda item: (item.anchor_date, item.display_label))
    return trip_instances
