from __future__ import annotations

from datetime import datetime, timedelta
from itertools import product

from app.models.base import AppState, FetchTargetStatus, utcnow
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.services.google_flights import build_google_flights_query_url_for_search
from app.services.ids import stable_id

def _app_state(app_state: AppState | None) -> AppState:
    return app_state or AppState()


def fetch_stagger_seconds(app_state: AppState | None = None) -> int:
    return _app_state(app_state).fetch_stagger_seconds


def fetch_interval_seconds(app_state: AppState | None = None) -> int:
    return _app_state(app_state).fetch_interval_seconds


# Compatibility exports for tests/callers that still import the default values directly.
FETCH_STAGGER_SECONDS = fetch_stagger_seconds()
FETCH_INTERVAL_SECONDS = fetch_interval_seconds()


def reconcile_fetch_targets(
    trackers: list[Tracker],
    trips: list[Trip],
    trip_instances: list[TripInstance],
    existing_targets: list[TrackerFetchTarget],
    *,
    now: datetime | None = None,
    app_state: AppState | None = None,
) -> list[TrackerFetchTarget]:
    existing_by_id = {target.fetch_target_id: target for target in existing_targets}
    trip_by_id = {trip.trip_id: trip for trip in trips}
    trip_instance_by_id = {instance.trip_instance_id: instance for instance in trip_instances}
    now = now or utcnow()
    desired: list[TrackerFetchTarget] = []
    reschedule_basis_by_id: dict[str, datetime] = {}
    immediate_target_ids: set[str] = set()

    for tracker in trackers:
        trip_instance = trip_instance_by_id.get(tracker.trip_instance_id)
        trip = trip_by_id.get(trip_instance.trip_id) if trip_instance else None
        schedule_offset_seconds = schedule_offset_for_trip(
            trip.created_at if trip else (trip_instance.created_at if trip_instance else tracker.created_at),
            app_state=app_state,
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
                fare_class_policy=tracker.fare_class_policy,
            )
            existing = existing_by_id.get(fetch_target_id)
            if existing:
                url_changed = existing.google_flights_url != google_flights_url
                definition_changed = existing.tracker_definition_signature != tracker.definition_signature
                offset_changed = existing.schedule_offset_seconds != schedule_offset_seconds
                existing.trip_instance_id = tracker.trip_instance_id
                existing.data_scope = tracker.data_scope
                existing.tracker_definition_signature = tracker.definition_signature
                existing.google_flights_url = google_flights_url
                existing.updated_at = utcnow()
                existing.schedule_offset_seconds = schedule_offset_seconds
                if offset_changed:
                    reschedule_basis_by_id[existing.fetch_target_id] = max(now, existing.last_fetch_finished_at or now)
                if url_changed or definition_changed:
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
                    immediate_target_ids.add(existing.fetch_target_id)
                desired.append(existing)
                continue
            desired.append(
                TrackerFetchTarget(
                    fetch_target_id=fetch_target_id,
                    tracker_id=tracker.tracker_id,
                    trip_instance_id=tracker.trip_instance_id,
                    data_scope=tracker.data_scope,
                    tracker_definition_signature=tracker.definition_signature,
                    origin_airport=origin_airport,
                    destination_airport=destination_airport,
                    schedule_offset_seconds=schedule_offset_seconds,
                    google_flights_url=google_flights_url,
                )
            )
            immediate_target_ids.add(fetch_target_id)

    desired.sort(key=lambda item: (item.trip_instance_id, item.origin_airport, item.destination_airport))
    next_immediate_at = now
    for target in desired:
        if target.fetch_target_id in immediate_target_ids:
            target.next_fetch_not_before = next_immediate_at
            next_immediate_at = next_immediate_at + timedelta(seconds=fetch_stagger_seconds(app_state))
        elif target.next_fetch_not_before is None or target.fetch_target_id in reschedule_basis_by_id:
            basis = reschedule_basis_by_id.get(target.fetch_target_id, max(now, target.last_fetch_finished_at or now))
            target.next_fetch_not_before = next_refresh_time(
                basis,
                target.schedule_offset_seconds,
                app_state=app_state,
            )
    return desired


def schedule_offset_for_trip(created_at: datetime, *, app_state: AppState | None = None) -> int:
    return int(created_at.timestamp()) % fetch_interval_seconds(app_state)


def next_refresh_time(
    after: datetime,
    schedule_offset_seconds: int,
    *,
    app_state: AppState | None = None,
) -> datetime:
    timestamp = int(after.timestamp())
    interval_seconds = fetch_interval_seconds(app_state)
    cycle_start = timestamp - (timestamp % interval_seconds)
    candidate_timestamp = cycle_start + schedule_offset_seconds
    if candidate_timestamp <= timestamp:
        candidate_timestamp += interval_seconds
    return after.fromtimestamp(candidate_timestamp, tz=after.tzinfo)
