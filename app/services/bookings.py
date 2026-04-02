from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import date, datetime

from app.models.base import UnmatchedBookingStatus, utcnow
from app.models.booking import Booking
from app.models.tracker import Tracker
from app.models.unmatched_booking import UnmatchedBooking
from app.route_options import time_in_window
from app.services.ids import new_id
from app.services.trips import save_trip
from app.storage.repository import Repository


@dataclass
class BookingCandidate:
    airline: str
    origin_airport: str
    destination_airport: str
    departure_date: date
    departure_time: str
    arrival_time: str
    booked_price: Decimal
    record_locator: str
    notes: str = ""


def _build_booking(
    candidate: BookingCandidate,
    *,
    source: str,
    trip_instance_id: str,
    tracker_id: str = "",
    notes: str | None = None,
) -> Booking:
    return Booking(
        booking_id=new_id("book"),
        source=source,
        trip_instance_id=trip_instance_id,
        tracker_id=tracker_id,
        airline=candidate.airline,
        origin_airport=candidate.origin_airport,
        destination_airport=candidate.destination_airport,
        departure_date=candidate.departure_date,
        departure_time=candidate.departure_time,
        arrival_time=candidate.arrival_time,
        booked_price=candidate.booked_price,
        record_locator=candidate.record_locator,
        notes=candidate.notes if notes is None else notes,
    )


def _save_booking(repository: Repository, booking: Booking) -> Booking:
    bookings = repository.load_bookings()
    bookings.append(booking)
    repository.save_bookings(bookings)
    return booking


def _matching_trackers_for_booking(candidate: BookingCandidate, trackers: list[Tracker]) -> list[Tracker]:
    matches: list[Tracker] = []
    for tracker in trackers:
        if tracker.travel_date != candidate.departure_date:
            continue
        if candidate.origin_airport not in tracker.origin_codes:
            continue
        if candidate.destination_airport not in tracker.destination_codes:
            continue
        if candidate.airline not in tracker.airline_codes:
            continue
        if not time_in_window(tracker.start_time, tracker.end_time, candidate.departure_time):
            continue
        matches.append(tracker)
    return matches


def record_booking(
    repository: Repository,
    candidate: BookingCandidate,
    *,
    trip_instance_id: str = "",
    tracker_id: str = "",
    source: str = "manual",
) -> tuple[Booking | None, UnmatchedBooking | None]:
    trip_instances = repository.load_trip_instances()
    trackers = repository.load_trackers()

    selected_trip = next((item for item in trip_instances if item.trip_instance_id == trip_instance_id), None) if trip_instance_id else None
    selected_tracker = next((item for item in trackers if item.tracker_id == tracker_id), None) if tracker_id else None

    if selected_tracker and selected_trip and selected_tracker.trip_instance_id != selected_trip.trip_instance_id:
        raise ValueError("Selected tracker does not belong to the chosen trip instance.")

    if selected_tracker:
        booking = _build_booking(
            candidate,
            source=source,
            trip_instance_id=selected_tracker.trip_instance_id,
            tracker_id=selected_tracker.tracker_id,
        )
        return _save_booking(repository, booking), None

    if selected_trip:
        candidate_trackers = [
            tracker
            for tracker in trackers
            if tracker.trip_instance_id == selected_trip.trip_instance_id
            and tracker.travel_date == candidate.departure_date
        ]
        matching_trackers = _matching_trackers_for_booking(candidate, candidate_trackers)
        booking = _build_booking(
            candidate,
            source=source,
            trip_instance_id=selected_trip.trip_instance_id,
            tracker_id=matching_trackers[0].tracker_id if len(matching_trackers) == 1 else "",
        )
        return _save_booking(repository, booking), None

    matching_trackers = _matching_trackers_for_booking(candidate, trackers)
    if len(matching_trackers) == 1:
        matched = matching_trackers[0]
        booking = _build_booking(
            candidate,
            source=source,
            trip_instance_id=matched.trip_instance_id,
            tracker_id=matched.tracker_id,
        )
        return _save_booking(repository, booking), None

    unmatched = UnmatchedBooking(
        unmatched_booking_id=new_id("ub"),
        source=source,
        airline=candidate.airline,
        origin_airport=candidate.origin_airport,
        destination_airport=candidate.destination_airport,
        departure_date=candidate.departure_date,
        departure_time=candidate.departure_time,
        arrival_time=candidate.arrival_time,
        booked_price=candidate.booked_price,
        record_locator=candidate.record_locator,
        raw_summary=f"{candidate.airline} {candidate.origin_airport}->{candidate.destination_airport} {candidate.departure_date.isoformat()} {candidate.departure_time}",
        candidate_trip_instance_ids="|".join(
            sorted({tracker.trip_instance_id for tracker in matching_trackers})
        ),
    )
    unmatched_bookings = repository.load_unmatched_bookings()
    unmatched_bookings.append(unmatched)
    repository.save_unmatched_bookings(unmatched_bookings)
    return None, unmatched


def resolve_unmatched_booking_to_trip_instance(
    repository: Repository,
    *,
    unmatched_booking_id: str,
    trip_instance_id: str,
) -> Booking:
    unmatched_bookings = repository.load_unmatched_bookings()
    unmatched = next((item for item in unmatched_bookings if item.unmatched_booking_id == unmatched_booking_id), None)
    if unmatched is None or unmatched.resolution_status != UnmatchedBookingStatus.OPEN:
        raise KeyError("Unmatched booking not found")

    trackers = repository.load_trackers()
    candidate = BookingCandidate(
        airline=unmatched.airline,
        origin_airport=unmatched.origin_airport,
        destination_airport=unmatched.destination_airport,
        departure_date=unmatched.departure_date,
        departure_time=unmatched.departure_time,
        arrival_time=unmatched.arrival_time,
        booked_price=unmatched.booked_price,
        record_locator=unmatched.record_locator,
    )
    matching_trackers = _matching_trackers_for_booking(
        candidate,
        [tracker for tracker in trackers if tracker.trip_instance_id == trip_instance_id],
    )

    booking = _build_booking(
        candidate,
        source=unmatched.source,
        trip_instance_id=trip_instance_id,
        tracker_id=matching_trackers[0].tracker_id if len(matching_trackers) == 1 else "",
        notes="Resolved from unmatched booking",
    )
    with repository.transaction():
        _save_booking(repository, booking)
        unmatched.resolution_status = UnmatchedBookingStatus.RESOLVED
        unmatched.updated_at = utcnow()
        repository.save_unmatched_bookings(unmatched_bookings)
    return booking


def create_one_time_trip_from_unmatched_booking(
    repository: Repository,
    *,
    unmatched_booking_id: str,
    trip_label: str,
) -> Booking:
    unmatched_bookings = repository.load_unmatched_bookings()
    unmatched = next((item for item in unmatched_bookings if item.unmatched_booking_id == unmatched_booking_id), None)
    if unmatched is None or unmatched.resolution_status != UnmatchedBookingStatus.OPEN:
        raise KeyError("Unmatched booking not found")

    departure = datetime.strptime(unmatched.departure_time, "%H:%M")
    departure_minutes = departure.hour * 60 + departure.minute
    start_minutes = max(0, departure_minutes - 60)
    end_minutes = min((23 * 60) + 59, departure_minutes + 120)
    start_time = f"{start_minutes // 60:02d}:{start_minutes % 60:02d}"
    end_time = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"

    trip = save_trip(
        repository,
        trip_id=None,
        label=trip_label,
        trip_kind="one_time",
        active=True,
        anchor_date=unmatched.departure_date,
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": unmatched.origin_airport,
                "destination_airports": unmatched.destination_airport,
                "airlines": unmatched.airline,
                "day_offset": 0,
                "start_time": start_time,
                "end_time": end_time,
            }
        ],
    )
    from app.services.workflows import sync_and_persist

    snapshot = sync_and_persist(repository)
    trip_instance = next(
        item
        for item in snapshot.trip_instances
        if item.trip_id == trip.trip_id and item.anchor_date == unmatched.departure_date
    )
    booking = resolve_unmatched_booking_to_trip_instance(
        repository,
        unmatched_booking_id=unmatched_booking_id,
        trip_instance_id=trip_instance.trip_instance_id,
    )
    return booking
