from __future__ import annotations

from datetime import date

from app.services.bookings import (
    BookingCandidate,
    create_one_time_trip_from_unmatched_booking,
    unlink_booking,
    record_booking,
    resolve_unmatched_booking_to_trip_instance,
)
from app.services.trips import save_trip
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


def seed_trip(repository: Repository) -> str:
    trip = save_trip(
        repository,
        trip_id=None,
        label="LA to SF Outbound",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 6),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX",
                "destination_airports": "SFO",
                "airlines": "Alaska|United",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )
    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    return next(item.trip_instance_id for item in snapshot.trip_instances if item.trip_id == trip.trip_id)


def test_record_booking_auto_matches_unique_trip_instance(repository: Repository) -> None:
    trip_instance_id = seed_trip(repository)

    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Alaska",
            origin_airport="BUR",
            destination_airport="SFO",
            departure_date=date(2026, 4, 6),
            departure_time="07:15",
            arrival_time="08:40",
            booked_price=121,
            record_locator="ABC123",
        ),
    )

    assert unmatched is None
    assert booking is not None
    assert booking.trip_instance_id == trip_instance_id


def test_unmatched_booking_can_be_linked_to_existing_trip_instance(repository: Repository) -> None:
    trip_instance_id = seed_trip(repository)

    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="United",
            origin_airport="LAX",
            destination_airport="SFO",
            departure_date=date(2026, 4, 7),
            departure_time="07:15",
            arrival_time="08:40",
            booked_price=149,
            record_locator="DEF456",
        ),
    )

    assert booking is None
    assert unmatched is not None

    linked = resolve_unmatched_booking_to_trip_instance(
        repository,
        unmatched_booking_id=unmatched.unmatched_booking_id,
        trip_instance_id=trip_instance_id,
    )

    assert linked.trip_instance_id == trip_instance_id
    assert repository.load_unmatched_bookings()[0].resolution_status == "resolved"


def test_unmatched_booking_can_create_new_one_time_trip(repository: Repository) -> None:
    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Delta",
            origin_airport="LAX",
            destination_airport="SEA",
            departure_date=date(2026, 5, 10),
            departure_time="00:30",
            arrival_time="02:55",
            booked_price=189,
            record_locator="ZZZ999",
        ),
    )

    assert booking is None
    assert unmatched is not None

    created_booking = create_one_time_trip_from_unmatched_booking(
        repository,
        unmatched_booking_id=unmatched.unmatched_booking_id,
        trip_label="Conference Arrival",
    )
    snapshot = sync_and_persist(repository, today=date(2026, 5, 1))

    assert created_booking.record_locator == "ZZZ999"
    assert any(trip.label == "Conference Arrival" for trip in snapshot.trips)


def test_linked_booking_can_be_unlinked_back_to_resolve(repository: Repository) -> None:
    trip_instance_id = seed_trip(repository)

    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Alaska",
            origin_airport="BUR",
            destination_airport="SFO",
            departure_date=date(2026, 4, 6),
            departure_time="07:15",
            arrival_time="08:40",
            booked_price=121,
            record_locator="UNLINK1",
        ),
    )

    assert booking is not None
    assert unmatched is None

    moved = unlink_booking(repository, booking_id=booking.booking_id)
    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))

    assert moved.unmatched_booking_id == booking.booking_id
    assert moved.candidate_trip_instance_ids == trip_instance_id
    assert not repository.load_bookings()
    assert any(item.unmatched_booking_id == booking.booking_id for item in repository.load_unmatched_bookings())
    instance = next(item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id)
    assert instance.travel_state == "planned"


def test_unmatched_booking_auto_links_when_matching_trip_is_created_later(repository: Repository) -> None:
    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Alaska",
            origin_airport="BUR",
            destination_airport="SFO",
            departure_date=date(2026, 4, 20),
            departure_time="07:15",
            arrival_time="08:40",
            booked_price=121,
            record_locator="LATE01",
        ),
    )

    assert booking is None
    assert unmatched is not None
    assert unmatched.resolution_status == "open"

    trip = save_trip(
        repository,
        trip_id=None,
        label="Late Match Trip",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 20),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance = next(item for item in snapshot.trip_instances if item.trip_id == trip.trip_id)
    saved_booking = next(item for item in repository.load_bookings() if item.record_locator == "LATE01")
    updated_unmatched = next(
        item for item in repository.load_unmatched_bookings() if item.unmatched_booking_id == unmatched.unmatched_booking_id
    )

    assert saved_booking.trip_instance_id == trip_instance.trip_instance_id
    assert updated_unmatched.resolution_status == "resolved"
    assert updated_unmatched.candidate_trip_instance_ids == trip_instance.trip_instance_id


def test_unmatched_booking_stays_open_when_multiple_matching_trips_exist(repository: Repository) -> None:
    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Alaska",
            origin_airport="BUR",
            destination_airport="SFO",
            departure_date=date(2026, 4, 22),
            departure_time="07:15",
            arrival_time="08:40",
            booked_price=121,
            record_locator="LATE02",
        ),
    )

    assert booking is None
    assert unmatched is not None

    for label in ["Ambiguous Trip A", "Ambiguous Trip B"]:
        save_trip(
            repository,
            trip_id=None,
            label=label,
            trip_kind="one_time",
            active=True,
            anchor_date=date(2026, 4, 22),
            anchor_weekday="",
            route_option_payloads=[
                {
                    "origin_airports": "BUR",
                    "destination_airports": "SFO",
                    "airlines": "Alaska",
                    "day_offset": 0,
                    "start_time": "06:00",
                    "end_time": "10:00",
                }
            ],
        )

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    candidate_ids = {
        item.trip_instance_id
        for item in snapshot.trip_instances
        if item.display_label in {"Ambiguous Trip A", "Ambiguous Trip B"}
    }
    updated_unmatched = next(
        item for item in repository.load_unmatched_bookings() if item.unmatched_booking_id == unmatched.unmatched_booking_id
    )

    assert not repository.load_bookings()
    assert updated_unmatched.resolution_status == "open"
    assert set(updated_unmatched.candidate_trip_instance_ids.split("|")) == candidate_ids
