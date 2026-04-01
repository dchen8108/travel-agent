from __future__ import annotations

from itertools import product

from app.models.base import FetchTargetStatus, utcnow
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.services.google_flights import build_google_flights_query_url_for_search
from app.services.ids import stable_id


def reconcile_fetch_targets(
    trackers: list[Tracker],
    existing_targets: list[TrackerFetchTarget],
) -> list[TrackerFetchTarget]:
    existing_by_id = {target.fetch_target_id: target for target in existing_targets}
    desired: list[TrackerFetchTarget] = []

    for tracker in trackers:
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
                existing.trip_instance_id = tracker.trip_instance_id
                existing.google_flights_url = google_flights_url
                existing.updated_at = utcnow()
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
                    existing.next_fetch_not_before = None
                    existing.last_fetch_started_at = None
                    existing.last_fetch_finished_at = None
                desired.append(existing)
                continue
            desired.append(
                TrackerFetchTarget(
                    fetch_target_id=fetch_target_id,
                    tracker_id=tracker.tracker_id,
                    trip_instance_id=tracker.trip_instance_id,
                    origin_airport=origin_airport,
                    destination_airport=destination_airport,
                    google_flights_url=google_flights_url,
                )
            )

    desired.sort(key=lambda item: (item.trip_instance_id, item.origin_airport, item.destination_airport))
    return desired
