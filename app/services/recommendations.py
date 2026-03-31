from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo

from app.models.base import TrackerStatus, TripStatus
from app.models.booking import Booking
from app.models.fare_observation import FareObservation
from app.models.program import Program
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance
from app.models.view_models import DashboardBuckets, TripContext
from app.settings import Settings


@dataclass
class TripRollup:
    trip: TripInstance
    trackers: list[Tracker]
    best_tracker: Tracker | None
    best_observation: FareObservation | None
    booking: Booking | None
    booking_tracker: Tracker | None
    booking_observation: FareObservation | None
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
        trip.best_outbound_summary = latest_summary(rollup.best_tracker, observations)
        trip.best_airline = rollup.best_observation.airline if rollup.best_observation else ""
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
            trackers=rollup.trackers,
            best_tracker=rollup.best_tracker,
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
    trackers_by_trip: dict[str, list[Tracker]] = defaultdict(list)
    for tracker in trackers:
        trackers_by_trip[tracker.trip_instance_id].append(tracker)
    for tracker_list in trackers_by_trip.values():
        tracker_list.sort(key=lambda tracker: (tracker.slot_rank, tracker.travel_date, tracker.slot_time_start))

    bookings_by_trip = {
        booking.trip_instance_id: booking
        for booking in bookings
        if booking.status == "active"
    }
    latest_by_tracker = latest_observation_by_tracker(observations)
    history_by_trip = history_totals_by_trip(observations, {tracker.tracker_id: tracker for tracker in trackers})

    rollups: list[TripRollup] = []
    for trip in sorted(trips, key=lambda item: (item.outbound_date, item.origin_airport, item.destination_airport)):
        trip_trackers = trackers_by_trip.get(trip.trip_instance_id, [])
        best_tracker, best_observation = best_tracker_for_trip(trip_trackers, latest_by_tracker)
        booking = bookings_by_trip.get(trip.trip_instance_id)
        booking_tracker = next(
            (tracker for tracker in trip_trackers if booking is not None and booking.tracker_id and tracker.tracker_id == booking.tracker_id),
            None,
        )
        booking_observation = latest_by_tracker.get(booking_tracker.tracker_id) if booking_tracker is not None else None
        latest_total = best_observation.price if best_observation else None
        historic_best = min(history_by_trip[trip.trip_instance_id]) if history_by_trip[trip.trip_instance_id] else None
        rollups.append(
            TripRollup(
                trip=trip,
                trackers=trip_trackers,
                best_tracker=best_tracker,
                best_observation=best_observation,
                booking=booking,
                booking_tracker=booking_tracker,
                booking_observation=booking_observation,
                latest_total=latest_total,
                historic_best_total=historic_best,
            )
        )
    return rollups


def best_tracker_for_trip(
    trackers: list[Tracker],
    latest_by_tracker: dict[str, FareObservation],
) -> tuple[Tracker | None, FareObservation | None]:
    candidates: list[tuple[Tracker, FareObservation]] = []
    for tracker in trackers:
        observation = latest_by_tracker.get(tracker.tracker_id)
        if observation is None:
            continue
        candidates.append((tracker, observation))
    if not candidates:
        return None, None
    best_tracker, best_observation = min(
        candidates,
        key=lambda item: (item[1].price, item[0].slot_rank, item[0].travel_date),
    )
    return best_tracker, best_observation


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
    grouped: dict[tuple[str, str], int] = {}
    for observation in observations:
        tracker = trackers_by_id.get(observation.tracker_id)
        if tracker is not None and tracker.segment_type != "outbound":
            continue
        batch_key = observation.source_id or observation.observed_at.isoformat()
        composite_key = (observation.trip_instance_id, batch_key)
        current = grouped.get(composite_key)
        if current is None or observation.price < current:
            grouped[composite_key] = observation.price
    history: dict[str, list[int]] = defaultdict(list)
    for (trip_instance_id, _), price in grouped.items():
        history[trip_instance_id].append(price)
    return history


def derive_trip_status(
    rollup: TripRollup,
    program: Program | None,
    settings: Settings,
) -> tuple[TripStatus, str]:
    ready_trackers = [tracker for tracker in rollup.trackers if tracker_ready(tracker)]
    if not ready_trackers:
        return TripStatus.NEEDS_TRACKER_SETUP, "Set up Google Flights tracking for at least one ranked slot before this trip can be monitored reliably."

    rebook_threshold = (
        program.rebook_alert_threshold
        if program is not None
        else settings.default_rebook_alert_threshold
    )

    if rollup.booking is not None:
        comparison_price = rollup.booking_observation.price if rollup.booking_observation is not None else None
        if comparison_price is not None and comparison_price <= rollup.booking.booked_price - rebook_threshold:
            savings = rollup.booking.booked_price - comparison_price
            if rollup.booking_tracker is not None:
                return TripStatus.REBOOK, f"Latest price for your booked slot is ${savings} below what you paid."
            return TripStatus.REBOOK, f"Best tracked slot is ${savings} below your booked fare."
        if rollup.booking_tracker is not None and rollup.booking_observation is None:
            return TripStatus.BOOKED_MONITORING, "Tracking is active, but your booked slot needs a fresh price signal before this trip can be evaluated for rebooking."
        if rollup.booking_tracker is None and rollup.latest_total is not None and rollup.latest_total <= rollup.booking.booked_price - rebook_threshold:
            savings = rollup.booking.booked_price - rollup.latest_total
            return TripStatus.REBOOK, f"Best tracked slot is ${savings} below your booked fare."
        return TripStatus.BOOKED_MONITORING, "Tracking is active and this booked trip is being monitored across your ranked slots."

    if rollup.latest_total is None:
        return TripStatus.WAIT, "Tracking is active, but no recent price signal has been observed for your ranked slots yet."

    today = datetime.now(ZoneInfo(settings.timezone)).date()
    trip_date = rollup.best_tracker.travel_date if rollup.best_tracker is not None else rollup.trip.outbound_date
    days_until_trip = max((trip_date - today).days, 0)
    if days_until_trip <= 28:
        return TripStatus.BOOK_NOW, "Recent price signal looks good for one of your ranked slots."

    if rollup.historic_best_total is not None and rollup.latest_total <= rollup.historic_best_total + rebook_threshold:
        return TripStatus.BOOK_NOW, "Current fare is near the best observed price across your ranked slots."

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
