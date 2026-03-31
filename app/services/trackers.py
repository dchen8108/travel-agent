from __future__ import annotations

from datetime import datetime
from urllib.parse import quote_plus

from app.models.base import SegmentType, TrackerStatus, TripMode
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance


def sync_trackers(
    trips: list[TripInstance],
    existing_trackers: list[Tracker] | None = None,
) -> tuple[list[TripInstance], list[Tracker]]:
    existing_by_id = {tracker.tracker_id: tracker for tracker in (existing_trackers or [])}
    trackers: list[Tracker] = []
    updated_trips: list[TripInstance] = []

    for trip in trips:
        outbound_tracker = build_tracker(trip, SegmentType.OUTBOUND, existing_by_id)
        trackers.append(outbound_tracker)
        trip.outbound_tracker_id = outbound_tracker.tracker_id
        if trip.trip_mode == TripMode.ROUND_TRIP and trip.return_date is not None:
            return_tracker = build_tracker(trip, SegmentType.RETURN, existing_by_id)
            trackers.append(return_tracker)
            trip.return_tracker_id = return_tracker.tracker_id
        else:
            trip.return_tracker_id = ""
        updated_trips.append(trip)

    return updated_trips, trackers


def build_tracker(
    trip: TripInstance,
    segment_type: SegmentType,
    existing_by_id: dict[str, Tracker],
) -> Tracker:
    tracker_id = stable_tracker_id(trip.trip_instance_id, segment_type)
    prior = existing_by_id.get(tracker_id)
    origin = trip.origin_airport if segment_type == SegmentType.OUTBOUND else trip.destination_airport
    destination = trip.destination_airport if segment_type == SegmentType.OUTBOUND else trip.origin_airport
    travel_date = trip.outbound_date if segment_type == SegmentType.OUTBOUND else trip.return_date
    if travel_date is None:
        raise ValueError("Return trackers require a return date.")
    generated_url = generate_google_flights_url(origin, destination, travel_date.isoformat())
    tracker = Tracker(
        tracker_id=tracker_id,
        trip_instance_id=trip.trip_instance_id,
        segment_type=segment_type,
        origin_airport=origin,
        destination_airport=destination,
        travel_date=travel_date,
        google_flights_url=prior.google_flights_url if prior and prior.google_flights_url else generated_url,
        link_source=prior.link_source if prior else "generated",
        tracking_status=prior.tracking_status if prior else TrackerStatus.NEEDS_SETUP,
        tracking_enabled_at=prior.tracking_enabled_at if prior else None,
        last_signal_at=prior.last_signal_at if prior else None,
        latest_observed_price=prior.latest_observed_price if prior else None,
        created_at=prior.created_at if prior else datetime.now().astimezone(),
    )
    if prior is not None:
        tracker.updated_at = prior.updated_at
    return tracker


def generate_google_flights_url(origin: str, destination: str, travel_date: str) -> str:
    query = quote_plus(f"Flights from {origin} to {destination} on {travel_date}")
    return f"https://www.google.com/travel/flights?q={query}"


def stable_tracker_id(trip_instance_id: str, segment_type: SegmentType) -> str:
    return f"trk_{trip_instance_id}_{segment_type.value}"


def mark_tracker_enabled(tracker: Tracker) -> Tracker:
    tracker.tracking_status = TrackerStatus.TRACKING_ENABLED
    tracker.tracking_enabled_at = tracker.tracking_enabled_at or datetime.now().astimezone()
    tracker.updated_at = datetime.now().astimezone()
    return tracker


def update_tracker_link(tracker: Tracker, url: str) -> Tracker:
    tracker.google_flights_url = url.strip()
    tracker.link_source = "manual"
    tracker.updated_at = datetime.now().astimezone()
    return tracker
