from __future__ import annotations

from datetime import datetime
from itertools import product

from app.models.base import FetchTargetStatus, utcnow
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.services.google_flights import build_google_flights_query_url_for_search
from app.services.ids import stable_id

FETCH_STAGGER_SECONDS = 10
FETCH_INTERVAL_SECONDS = 4 * 60 * 60


def reconcile_fetch_targets(
    trackers: list[Tracker],
    trips: list[Trip],
    trip_instances: list[TripInstance],
    existing_targets: list[TrackerFetchTarget],
) -> list[TrackerFetchTarget]:
    existing_by_id = {target.fetch_target_id: target for target in existing_targets}
    trip_by_id = {trip.trip_id: trip for trip in trips}
    trip_instance_by_id = {instance.trip_instance_id: instance for instance in trip_instances}
    now = utcnow()
    desired: list[TrackerFetchTarget] = []
    reschedule_basis_by_id: dict[str, datetime] = {}

    for tracker in trackers:
        trip_instance = trip_instance_by_id.get(tracker.trip_instance_id)
        trip = trip_by_id.get(trip_instance.trip_id) if trip_instance else None
        schedule_offset_seconds = schedule_offset_for_trip(
            trip.created_at if trip else (trip_instance.created_at if trip_instance else tracker.created_at)
        )
        for origin_airport, destination_airport in product(tracker.origin_codes, tracker.destination_codes):
            fetch_target_id = stable_id("ft", tracker.tracker_id, origin_airport, destination_airport)
            google_flights_url = build_google_flights_query_url_for_search(
                travel_date=tracker.travel_date.isoformat(),
                origin_airport=origin_airport,
                destination_airport=destination_airport,
                airline_codes=tracker.airline_codes,
                start_time=tracker.start_time,
                end_time=tracker.end_time,
            )
            existing = existing_by_id.get(fetch_target_id)
            if existing:
                url_changed = existing.google_flights_url != google_flights_url
                offset_changed = existing.schedule_offset_seconds != schedule_offset_seconds
                existing.trip_instance_id = tracker.trip_instance_id
                existing.google_flights_url = google_flights_url
                existing.updated_at = utcnow()
                existing.schedule_offset_seconds = schedule_offset_seconds
                if offset_changed:
                    reschedule_basis_by_id[existing.fetch_target_id] = max(now, existing.last_fetch_finished_at or now)
                if url_changed:
                    existing.latest_price = None
                    existing.latest_airline = ""
                    existing.latest_departure_label = ""
                    existing.latest_arrival_label = ""
                    existing.latest_summary = ""
                    existing.latest_fetched_at = None
                    existing.last_fetch_status = FetchTargetStatus.PENDING
                    existing.last_fetch_error = ""
                    existing.consecutive_failures = 0
                    existing.last_fetch_started_at = None
                    existing.last_fetch_finished_at = None
                    reschedule_basis_by_id[existing.fetch_target_id] = now
                desired.append(existing)
                continue
            desired.append(
                TrackerFetchTarget(
                    fetch_target_id=fetch_target_id,
                    tracker_id=tracker.tracker_id,
                    trip_instance_id=tracker.trip_instance_id,
                    origin_airport=origin_airport,
                    destination_airport=destination_airport,
                    schedule_offset_seconds=schedule_offset_seconds,
                    google_flights_url=google_flights_url,
                )
            )
            reschedule_basis_by_id[fetch_target_id] = now

    desired.sort(key=lambda item: (item.trip_instance_id, item.origin_airport, item.destination_airport))
    for target in desired:
        if target.next_fetch_not_before is None or target.fetch_target_id in reschedule_basis_by_id:
            basis = reschedule_basis_by_id.get(target.fetch_target_id, max(now, target.last_fetch_finished_at or now))
            target.next_fetch_not_before = next_refresh_time(basis, target.schedule_offset_seconds)
    return desired


def schedule_offset_for_trip(created_at: datetime) -> int:
    return int(created_at.timestamp()) % FETCH_INTERVAL_SECONDS


def next_refresh_time(after: datetime, schedule_offset_seconds: int) -> datetime:
    timestamp = int(after.timestamp())
    cycle_start = timestamp - (timestamp % FETCH_INTERVAL_SECONDS)
    candidate_timestamp = cycle_start + schedule_offset_seconds
    if candidate_timestamp <= timestamp:
        candidate_timestamp += FETCH_INTERVAL_SECONDS
    return after.fromtimestamp(candidate_timestamp, tz=after.tzinfo)
