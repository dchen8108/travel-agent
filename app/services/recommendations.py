from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from app.models.base import RecommendationState, TrackerStatus, TravelState, utcnow
from app.models.booking import Booking
from app.models.fare_observation import FareObservation
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip_instance import TripInstance


def refresh_tracker_projections(
    trackers: list[Tracker],
    observations: list[FareObservation],
) -> list[Tracker]:
    latest_by_tracker: dict[str, FareObservation] = {}
    for observation in observations:
        current = latest_by_tracker.get(observation.tracker_id)
        if current is None or observation.observed_at > current.observed_at:
            latest_by_tracker[observation.tracker_id] = observation
        elif observation.observed_at == current.observed_at and observation.price < current.price:
            latest_by_tracker[observation.tracker_id] = observation

    for tracker in trackers:
        latest = latest_by_tracker.get(tracker.tracker_id)
        if latest is None:
            continue
        tracker.latest_observed_price = latest.price
        tracker.last_signal_at = latest.observed_at
        tracker.latest_fetched_at = None
        tracker.latest_winning_origin_airport = ""
        tracker.latest_winning_destination_airport = ""
        tracker.latest_match_summary = latest.match_summary
        tracker.latest_signal_source = "manual_import"
        tracker.tracking_status = TrackerStatus.SIGNAL_RECEIVED
        tracker.updated_at = utcnow()
    return trackers


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
                tracker.tracking_status = TrackerStatus.TRACKING_ENABLED
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
                tracker.tracking_status = TrackerStatus.TRACKING_ENABLED
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
        tracker.tracking_status = TrackerStatus.SIGNAL_RECEIVED
        tracker.updated_at = utcnow()
    return trackers


def best_tracker_for_instance(trackers: list[Tracker]) -> Tracker | None:
    with_prices = [tracker for tracker in trackers if tracker.latest_observed_price is not None]
    if not with_prices:
        return None
    return min(with_prices, key=lambda item: (item.latest_observed_price or 10**9, item.rank))


def recompute_trip_states(
    trip_instances: list[TripInstance],
    trackers: list[Tracker],
    bookings: list[Booking],
    observations: list[FareObservation],
) -> list[TripInstance]:
    trackers_by_instance: dict[str, list[Tracker]] = defaultdict(list)
    observations_by_instance: dict[str, list[FareObservation]] = defaultdict(list)
    active_booking_by_instance: dict[str, Booking] = {}

    for tracker in trackers:
        trackers_by_instance[tracker.trip_instance_id].append(tracker)
    for observation in observations:
        observations_by_instance[observation.trip_instance_id].append(observation)
    for booking in bookings:
        if booking.status == "active":
            active_booking_by_instance[booking.trip_instance_id] = booking

    for instance in trip_instances:
        related_trackers = sorted(trackers_by_instance.get(instance.trip_instance_id, []), key=lambda item: item.rank)
        related_observations = observations_by_instance.get(instance.trip_instance_id, [])
        booking = active_booking_by_instance.get(instance.trip_instance_id)
        best_tracker = best_tracker_for_instance(related_trackers)
        booked_tracker = next(
            (tracker for tracker in related_trackers if booking and booking.tracker_id and tracker.tracker_id == booking.tracker_id),
            None,
        )
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
            instance.recommendation_state = RecommendationState.WAIT
            instance.recommendation_reason = "Occurrence skipped."
            instance.updated_at = utcnow()
            continue

        if booking:
            comparison_tracker = booked_tracker if booked_tracker else best_tracker
            if booked_tracker and booked_tracker.latest_observed_price is None:
                instance.recommendation_state = RecommendationState.BOOKED_MONITORING
                instance.recommendation_reason = "Monitoring for a refreshed price on the booked route option."
            elif comparison_tracker and comparison_tracker.latest_observed_price is not None and comparison_tracker.latest_observed_price < booking.booked_price:
                instance.recommendation_state = RecommendationState.REBOOK
                instance.recommendation_reason = (
                    f"Latest matched price ${comparison_tracker.latest_observed_price} is below your booked price ${booking.booked_price}."
                )
            else:
                instance.recommendation_state = RecommendationState.BOOKED_MONITORING
                instance.recommendation_reason = "Monitoring for a lower matched price."
            instance.updated_at = utcnow()
            continue

        if is_past:
            instance.recommendation_state = RecommendationState.WAIT
            instance.recommendation_reason = "Past trip. Tracker setup is no longer needed."
            instance.updated_at = utcnow()
            continue

        if not related_trackers or all(tracker.tracking_status == TrackerStatus.NEEDS_SETUP for tracker in related_trackers):
            instance.recommendation_state = RecommendationState.NEEDS_TRACKER_SETUP
            instance.recommendation_reason = "Set up at least one Google Flights tracker for this trip."
            instance.updated_at = utcnow()
            continue

        if best_tracker is None or best_tracker.latest_observed_price is None:
            instance.recommendation_state = RecommendationState.WAIT
            instance.recommendation_reason = "Tracking is enabled, but there is no usable price signal yet."
            instance.updated_at = utcnow()
            continue

        historical_low = min((observation.price for observation in related_observations), default=best_tracker.latest_observed_price)
        latest_observation = next(
            (
                observation
                for observation in sorted(related_observations, key=lambda item: item.observed_at, reverse=True)
                if observation.tracker_id == best_tracker.tracker_id
            ),
            None,
        )
        if latest_observation and (
            latest_observation.price_direction == "dropped" or best_tracker.latest_observed_price <= historical_low
        ):
            instance.recommendation_state = RecommendationState.BOOK_NOW
            instance.recommendation_reason = f"Best matched price is ${best_tracker.latest_observed_price} and at or near the best observed level."
        else:
            instance.recommendation_state = RecommendationState.WAIT
            instance.recommendation_reason = f"Latest matched price is ${best_tracker.latest_observed_price}; keep monitoring for now."
        instance.updated_at = utcnow()

    trip_instances.sort(key=lambda item: (item.anchor_date, item.display_label))
    return trip_instances
