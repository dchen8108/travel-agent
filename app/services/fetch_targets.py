from __future__ import annotations

from datetime import datetime
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


FETCH_STAGGER_SECONDS = fetch_stagger_seconds()


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
    trip_instance_by_id = {instance.trip_instance_id: instance for instance in trip_instances}
    now = now or utcnow()
    desired: list[TrackerFetchTarget] = []

    for tracker in trackers:
        trip_instance = trip_instance_by_id.get(tracker.trip_instance_id)
        for origin_airport, destination_airport in product(tracker.origin_codes, tracker.destination_codes):
            fetch_target_id = stable_id("ft", tracker.tracker_id, origin_airport, destination_airport)
            google_flights_url = build_google_flights_query_url_for_search(
                travel_date=tracker.travel_date.isoformat(),
                origin_airport=origin_airport,
                destination_airport=destination_airport,
                airline_codes=tracker.airline_codes,
                start_time=tracker.start_time,
                end_time=tracker.end_time,
                stops=tracker.stops,
                fare_class=tracker.fare_class,
            )
            existing = existing_by_id.get(fetch_target_id)
            if existing:
                url_changed = existing.google_flights_url != google_flights_url
                definition_changed = existing.tracker_definition_signature != tracker.definition_signature
                existing.trip_instance_id = tracker.trip_instance_id
                existing.data_scope = tracker.data_scope
                existing.tracker_definition_signature = tracker.definition_signature
                existing.google_flights_url = google_flights_url
                existing.updated_at = utcnow()
                if url_changed or definition_changed:
                    existing.latest_price = None
                    existing.latest_airline = ""
                    existing.latest_stops = ""
                    existing.latest_departure_label = ""
                    existing.latest_arrival_label = ""
                    existing.latest_summary = ""
                    existing.latest_fetched_at = None
                    existing.last_fetch_status = FetchTargetStatus.PENDING
                    existing.last_fetch_error = ""
                    existing.consecutive_failures = 0
                    existing.last_fetch_started_at = None
                    existing.last_fetch_finished_at = None
                    existing.refresh_requested_at = now
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
                    google_flights_url=google_flights_url,
                    refresh_requested_at=now,
                )
            )

    desired.sort(key=lambda item: (item.trip_instance_id, item.origin_airport, item.destination_airport))
    return desired
