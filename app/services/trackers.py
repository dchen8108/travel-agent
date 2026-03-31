from __future__ import annotations

from datetime import date, datetime
from urllib.parse import quote_plus

from app.models.base import SegmentType, TrackerStatus
from app.models.program import Program
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance
from app.route_details import RankedRouteDetail, parse_route_detail_rankings
from app.services.trip_instances import detail_date_from_anchor


def sync_trackers(
    trips: list[TripInstance],
    existing_trackers: list[Tracker] | None = None,
    programs_by_id: dict[str, Program] | None = None,
    today: date | None = None,
) -> tuple[list[TripInstance], list[Tracker]]:
    existing_by_id = {tracker.tracker_id: tracker for tracker in (existing_trackers or [])}
    trackers: list[Tracker] = []
    updated_trips: list[TripInstance] = []
    programs_by_id = programs_by_id or {}
    current_day = today or datetime.now().astimezone().date()

    for trip in trips:
        program = programs_by_id.get(trip.program_id)
        if program is None:
            updated_trips.append(trip)
            continue
        route_details = parse_route_detail_rankings(program.route_detail_rankings)
        primary_weekday = route_details[0].weekday
        detail_trackers: list[Tracker] = []
        for index, detail in enumerate(route_details):
            tracker = build_tracker(
                trip,
                detail,
                detail_rank=index + 1,
                primary_weekday=primary_weekday,
                existing_by_id=existing_by_id,
                today=current_day,
            )
            if tracker is not None:
                detail_trackers.append(tracker)
        trackers.extend(detail_trackers)
        trip.outbound_tracker_id = detail_trackers[0].tracker_id if detail_trackers else ""
        if detail_trackers:
            trip.origin_airport = detail_trackers[0].origin_airport
            trip.destination_airport = detail_trackers[0].destination_airport
        updated_trips.append(trip)

    return updated_trips, trackers


def build_tracker(
    trip: TripInstance,
    detail: RankedRouteDetail,
    *,
    detail_rank: int,
    primary_weekday,
    existing_by_id: dict[str, Tracker],
    today: date,
) -> Tracker | None:
    tracker_id = stable_tracker_id(trip.trip_instance_id, detail)
    prior = existing_by_id.get(tracker_id)
    travel_date = detail_date_from_anchor(trip.outbound_date, primary_weekday, detail.weekday)
    if travel_date < today:
        return None
    generated_url = generate_google_flights_url(detail, travel_date.isoformat())
    tracker = Tracker(
        tracker_id=tracker_id,
        trip_instance_id=trip.trip_instance_id,
        segment_type=SegmentType.OUTBOUND,
        detail_rank=detail_rank,
        detail_weekday=str(detail.weekday),
        detail_time_start=detail.start_time,
        detail_time_end=detail.end_time,
        detail_airline=detail.airline,
        detail_nonstop_only=detail.nonstop_only,
        origin_airport=detail.origin_airport,
        destination_airport=detail.destination_airport,
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


def generate_google_flights_url(detail: RankedRouteDetail, travel_date: str) -> str:
    query_parts = [
        f"Flights from {detail.origin_airport} to {detail.destination_airport} on {travel_date}",
        f"between {detail.start_time} and {detail.end_time}",
    ]
    if detail.airline:
        query_parts.append(f"on {detail.airline}")
    if detail.nonstop_only:
        query_parts.append("nonstop")
    query = quote_plus(" ".join(query_parts))
    return f"https://www.google.com/travel/flights?q={query}"


def stable_tracker_id(trip_instance_id: str, detail: RankedRouteDetail) -> str:
    return f"trk_{trip_instance_id}_{detail.slug}"


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
