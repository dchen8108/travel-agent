from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from app.models.program import Program
from app.models.base import SegmentType, TrackerStatus, TripStatus
from app.models.booking import Booking
from app.models.fare_observation import FareObservation
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance
from app.models.view_models import DashboardBuckets, TripContext
from app.settings import Settings


@dataclass
class TripRollup:
    trip: TripInstance
    outbound_tracker: Tracker | None
    return_tracker: Tracker | None
    booking: Booking | None
    outbound_price: int | None
    return_price: int | None
    latest_total: int | None
    historic_best_total: int | None


def recompute_trip_states(
    trips: list[TripInstance],
    trackers: list[Tracker],
    bookings: list[Booking],
    observations: list[FareObservation],
    programs: list[Program],
    settings: Settings,
) -> list[TripInstance]:
    rollups = build_trip_rollups(trips, trackers, bookings, observations)
    programs_by_id = {program.program_id: program for program in programs}
    updated: list[TripInstance] = []
    now = datetime.now().astimezone()
    for rollup in rollups:
        trip = rollup.trip
        trip.last_checked_at = now
        trip.best_price = rollup.latest_total
        trip.best_outbound_summary = latest_summary(rollup.outbound_tracker, observations)
        trip.best_return_summary = latest_summary(rollup.return_tracker, observations)
        trip.best_airline = summarize_airlines(rollup.outbound_tracker, rollup.return_tracker, observations)
        trip.updated_at = now
        program = programs_by_id.get(trip.program_id)
        trip.status, trip.recommendation_reason = derive_trip_status(rollup, program, settings)
        updated.append(trip)
    return updated


def build_dashboard_buckets(
    trips: list[TripInstance],
    trackers: list[Tracker],
    bookings: list[Booking],
    observations: list[FareObservation],
) -> DashboardBuckets:
    buckets = DashboardBuckets()
    for rollup in build_trip_rollups(trips, trackers, bookings, observations):
        context = TripContext(
            trip=rollup.trip,
            outbound_tracker=rollup.outbound_tracker,
            return_tracker=rollup.return_tracker,
            booking=rollup.booking,
            latest_total_price=rollup.latest_total,
        )
        if rollup.trip.status == TripStatus.NEEDS_TRACKER_SETUP:
            buckets.setup.append(context)
        elif rollup.trip.status in {TripStatus.BOOKED_MONITORING, TripStatus.REBOOK}:
            buckets.booked.append(context)
        else:
            buckets.action.append(context)
    return buckets


def build_trip_rollups(
    trips: list[TripInstance],
    trackers: list[Tracker],
    bookings: list[Booking],
    observations: list[FareObservation],
) -> list[TripRollup]:
    trackers_by_id = {tracker.tracker_id: tracker for tracker in trackers}
    bookings_by_trip = {
        booking.trip_instance_id: booking
        for booking in bookings
        if booking.status == "active"
    }
    latest_by_tracker = latest_observation_by_tracker(observations)
    history_by_trip = history_totals_by_trip(observations, trackers_by_id)

    rollups: list[TripRollup] = []
    for trip in sorted(trips, key=lambda item: (item.outbound_date, item.origin_airport, item.destination_airport)):
        outbound_tracker = trackers_by_id.get(trip.outbound_tracker_id)
        return_tracker = trackers_by_id.get(trip.return_tracker_id)
        outbound_price = latest_by_tracker.get(trip.outbound_tracker_id)
        return_price = latest_by_tracker.get(trip.return_tracker_id)
        latest_total = (
            outbound_price.price + return_price.price
            if outbound_price is not None and return_price is not None
            else None
        )
        historic_best = min(history_by_trip[trip.trip_instance_id]) if history_by_trip[trip.trip_instance_id] else None
        rollups.append(
            TripRollup(
                trip=trip,
                outbound_tracker=outbound_tracker,
                return_tracker=return_tracker,
                booking=bookings_by_trip.get(trip.trip_instance_id),
                outbound_price=outbound_price.price if outbound_price else None,
                return_price=return_price.price if return_price else None,
                latest_total=latest_total,
                historic_best_total=historic_best,
            )
        )
    return rollups


def latest_observation_by_tracker(observations: Iterable[FareObservation]) -> dict[str, FareObservation]:
    latest: dict[str, FareObservation] = {}
    for observation in observations:
        current = latest.get(observation.tracker_id)
        if current is None:
            latest[observation.tracker_id] = observation
            continue
        if observation.observed_at > current.observed_at:
            latest[observation.tracker_id] = observation
            continue
        if observation.observed_at == current.observed_at and observation.price < current.price:
            latest[observation.tracker_id] = observation
    return latest


def history_totals_by_trip(
    observations: Iterable[FareObservation],
    trackers_by_id: dict[str, Tracker],
) -> dict[str, list[int]]:
    grouped: dict[tuple[str, str], dict[SegmentType, int]] = defaultdict(dict)
    for observation in observations:
        date_key = observation.observed_at.date().isoformat()
        bucket = grouped[(observation.trip_instance_id, date_key)]
        current = bucket.get(observation.segment_type)
        if current is None or observation.price < current:
            bucket[observation.segment_type] = observation.price
    history: dict[str, list[int]] = defaultdict(list)
    for (trip_instance_id, _), prices in grouped.items():
        if SegmentType.OUTBOUND in prices and SegmentType.RETURN in prices:
            history[trip_instance_id].append(prices[SegmentType.OUTBOUND] + prices[SegmentType.RETURN])
    return history


def derive_trip_status(
    rollup: TripRollup,
    program: Program | None,
    settings: Settings,
) -> tuple[TripStatus, str]:
    trackers_ready = tracker_ready(rollup.outbound_tracker) and tracker_ready(rollup.return_tracker)
    if not trackers_ready:
        return TripStatus.NEEDS_TRACKER_SETUP, "Set up outbound and return Google Flights tracking before this trip can be monitored reliably."

    rebook_threshold = (
        program.rebook_alert_threshold
        if program is not None
        else settings.default_rebook_alert_threshold
    )

    if rollup.booking is not None:
        if rollup.latest_total is not None and rollup.latest_total <= rollup.booking.booked_price - rebook_threshold:
            savings = rollup.booking.booked_price - rollup.latest_total
            return TripStatus.REBOOK, f"Latest segment prices are ${savings} below your booked total."
        return TripStatus.BOOKED_MONITORING, "Tracking is active and this booked trip is being monitored for a better price."

    if rollup.latest_total is None:
        return TripStatus.WAIT, "Tracking is active, but both segment prices have not been observed yet."

    days_until_trip = max((rollup.trip.outbound_date - datetime.now().date()).days, 0)
    if days_until_trip <= 28:
        return TripStatus.BOOK_NOW, "Recent price signal looks good for this trip."

    if rollup.historic_best_total is not None and rollup.latest_total <= rollup.historic_best_total + rebook_threshold:
        return TripStatus.BOOK_NOW, "Current combined price is near the best observed total for this trip."

    return TripStatus.WAIT, "Tracking is active, but the latest signal does not justify booking yet."


def tracker_ready(tracker: Tracker | None) -> bool:
    if tracker is None:
        return False
    return tracker.tracking_status in {
        TrackerStatus.TRACKING_ENABLED,
        TrackerStatus.SIGNAL_RECEIVED,
        TrackerStatus.STALE,
    }


def latest_summary(
    tracker: Tracker | None,
    observations: Iterable[FareObservation],
) -> str:
    if tracker is None:
        return ""
    latest: FareObservation | None = None
    for observation in observations:
        if observation.tracker_id != tracker.tracker_id:
            continue
        if latest is None:
            latest = observation
            continue
        if observation.observed_at > latest.observed_at:
            latest = observation
            continue
        if observation.observed_at == latest.observed_at and observation.price < latest.price:
            latest = observation
    if latest is None:
        return ""
    return latest.outbound_summary or latest.return_summary


def summarize_airlines(
    outbound_tracker: Tracker | None,
    return_tracker: Tracker | None,
    observations: Iterable[FareObservation],
) -> str:
    latest_by_tracker = latest_observation_by_tracker(observations)
    outbound = latest_by_tracker.get(outbound_tracker.tracker_id) if outbound_tracker else None
    inbound = latest_by_tracker.get(return_tracker.tracker_id) if return_tracker else None
    airlines = [item.airline for item in (outbound, inbound) if item and item.airline]
    if not airlines:
        return ""
    if len(set(airlines)) == 1:
        return airlines[0]
    return " / ".join(airlines)
