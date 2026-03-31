from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.models.base import TrackerStatus, TravelState, utcnow
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance
from app.route_options import travel_date_for_offset
from app.services.google_flights import build_google_flights_query_url
from app.services.ids import stable_id


def reconcile_trackers(
    trip_instances: list[TripInstance],
    route_options: list[RouteOption],
    existing_trackers: list[Tracker],
    *,
    today: date,
) -> list[Tracker]:
    route_options_by_trip: dict[str, list[RouteOption]] = defaultdict(list)
    for option in route_options:
        route_options_by_trip[option.trip_id].append(option)
    for options in route_options_by_trip.values():
        options.sort(key=lambda item: item.rank)

    existing_by_id = {tracker.tracker_id: tracker for tracker in existing_trackers}
    desired: list[Tracker] = []
    desired_ids: set[str] = set()

    for instance in trip_instances:
        if instance.travel_state == TravelState.SKIPPED:
            continue
        options = route_options_by_trip.get(instance.trip_id, [])
        for option in options:
            tracker_id = stable_id("trk", instance.trip_instance_id, option.route_option_id)
            desired_ids.add(tracker_id)
            existing = existing_by_id.get(tracker_id)
            generated_url = build_google_flights_query_url(
                Tracker(
                    tracker_id=tracker_id,
                    trip_instance_id=instance.trip_instance_id,
                    route_option_id=option.route_option_id,
                    rank=option.rank,
                    origin_airports=option.origin_airports,
                    destination_airports=option.destination_airports,
                    airlines=option.airlines,
                    day_offset=option.day_offset,
                    travel_date=travel_date_for_offset(instance.anchor_date, option.day_offset),
                    start_time=option.start_time,
                    end_time=option.end_time,
                )
            )
            if existing:
                existing.rank = option.rank
                existing.origin_airports = option.origin_airports
                existing.destination_airports = option.destination_airports
                existing.airlines = option.airlines
                existing.day_offset = option.day_offset
                existing.travel_date = travel_date_for_offset(instance.anchor_date, option.day_offset)
                existing.start_time = option.start_time
                existing.end_time = option.end_time
                if existing.link_source != "manual" or not existing.google_flights_url:
                    existing.google_flights_url = generated_url
                    existing.link_source = "generated"
                if existing.last_signal_at and (today - existing.last_signal_at.date()).days > 7:
                    existing.tracking_status = TrackerStatus.STALE
                existing.updated_at = utcnow()
                desired.append(existing)
                continue
            desired.append(
                Tracker(
                    tracker_id=tracker_id,
                    trip_instance_id=instance.trip_instance_id,
                    route_option_id=option.route_option_id,
                    rank=option.rank,
                    origin_airports=option.origin_airports,
                    destination_airports=option.destination_airports,
                    airlines=option.airlines,
                    day_offset=option.day_offset,
                    travel_date=travel_date_for_offset(instance.anchor_date, option.day_offset),
                    start_time=option.start_time,
                    end_time=option.end_time,
                    google_flights_url=generated_url,
                )
            )

    desired.sort(key=lambda item: (item.travel_date, item.rank, item.trip_instance_id))
    return desired
