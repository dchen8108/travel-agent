from __future__ import annotations

from datetime import date, datetime
from urllib.parse import quote_plus

from app.models.base import SegmentType, TrackerStatus
from app.models.program import Program
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance
from app.services.trip_instances import slot_date_from_anchor
from app.time_slots import RankedTimeSlot, parse_time_slot_rankings


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
        slots = parse_time_slot_rankings(program.time_slot_rankings)
        slot_trackers: list[Tracker] = []
        for index, slot in enumerate(slots):
            tracker = build_tracker(
                trip,
                slot,
                slot_rank=index + 1,
                primary_weekday=slots[0].weekday,
                existing_by_id=existing_by_id,
                today=current_day,
            )
            if tracker is not None:
                slot_trackers.append(tracker)
        trackers.extend(slot_trackers)
        trip.outbound_tracker_id = slot_trackers[0].tracker_id if slot_trackers else ""
        updated_trips.append(trip)

    return updated_trips, trackers


def build_tracker(
    trip: TripInstance,
    slot: RankedTimeSlot,
    *,
    slot_rank: int,
    primary_weekday,
    existing_by_id: dict[str, Tracker],
    today: date,
) -> Tracker | None:
    tracker_id = stable_tracker_id(trip.trip_instance_id, slot)
    prior = existing_by_id.get(tracker_id)
    travel_date = slot_date_from_anchor(trip.outbound_date, primary_weekday, slot.weekday)
    if travel_date < today:
        return None
    generated_url = generate_google_flights_url(
        trip.origin_airport,
        trip.destination_airport,
        travel_date.isoformat(),
        slot.start_time,
        slot.end_time,
    )
    tracker = Tracker(
        tracker_id=tracker_id,
        trip_instance_id=trip.trip_instance_id,
        segment_type=SegmentType.OUTBOUND,
        slot_rank=slot_rank,
        slot_weekday=str(slot.weekday),
        slot_time_start=slot.start_time,
        slot_time_end=slot.end_time,
        origin_airport=trip.origin_airport,
        destination_airport=trip.destination_airport,
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


def generate_google_flights_url(
    origin: str,
    destination: str,
    travel_date: str,
    start_time: str,
    end_time: str,
) -> str:
    query = quote_plus(
        f"Flights from {origin} to {destination} on {travel_date} between {start_time} and {end_time}"
    )
    return f"https://www.google.com/travel/flights?q={query}"


def stable_tracker_id(trip_instance_id: str, slot: RankedTimeSlot) -> str:
    return f"trk_{trip_instance_id}_{slot.slug}"


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
