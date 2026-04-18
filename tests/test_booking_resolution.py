from __future__ import annotations

from datetime import date

import pytest

from app.services.bookings import (
    BookingCandidate,
    unlink_booking,
    record_booking,
    resolve_unmatched_booking_to_trip,
    resolve_unmatched_booking_to_trip_instance,
    update_booking,
    update_unmatched_booking,
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


def test_record_booking_requires_arrival_day_offset_for_overnight_arrivals(repository: Repository) -> None:
    trip_instance_id = seed_trip(repository)

    with pytest.raises(ValueError, match="Arrival must be after departure"):
        record_booking(
            repository,
            BookingCandidate(
                airline="Alaska",
                origin_airport="BUR",
                destination_airport="SFO",
                departure_date=date(2026, 4, 6),
                departure_time="23:30",
                arrival_time="01:10",
                booked_price=121,
                record_locator="OVERN1",
            ),
            trip_instance_id=trip_instance_id,
        )


def test_record_booking_auto_matches_unique_trip_instance(repository: Repository) -> None:
    trip_instance_id = seed_trip(repository)
    route_option_id = repository.load_route_options()[0].route_option_id

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
    assert booking.route_option_id == route_option_id


def test_boundary_departure_matches_later_adjacent_route_option(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Boundary Match Trip",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 6),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "11:00",
                "end_time": "12:00",
            },
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "12:00",
                "end_time": "13:00",
            },
        ],
    )
    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance_id = next(item.trip_instance_id for item in snapshot.trip_instances if item.trip_id == trip.trip_id)
    route_options = sorted(
        [item for item in repository.load_route_options() if item.trip_id == trip.trip_id],
        key=lambda item: item.rank,
    )

    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Alaska",
            origin_airport="BUR",
            destination_airport="SFO",
            departure_date=date(2026, 4, 6),
            departure_time="12:00",
            arrival_time="13:15",
            booked_price=121,
            record_locator="BOUND1",
        ),
    )

    assert unmatched is None
    assert booking is not None
    assert booking.trip_instance_id == trip_instance_id
    assert booking.route_option_id == route_options[1].route_option_id


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
    assert linked.route_option_id == ""
    assert repository.load_unmatched_bookings() == []


def test_unmatched_booking_link_rejects_missing_trip_instance(repository: Repository) -> None:
    _trip_instance_id = seed_trip(repository)

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
            record_locator="BAD999",
        ),
    )

    assert booking is None
    assert unmatched is not None

    try:
        resolve_unmatched_booking_to_trip_instance(
            repository,
            unmatched_booking_id=unmatched.unmatched_booking_id,
            trip_instance_id="inst_missing",
        )
    except KeyError as exc:
        assert str(exc) == "'Scheduled trip not found'"
    else:
        raise AssertionError("Expected missing scheduled trip to be rejected")

    assert repository.load_unmatched_bookings() != []
    assert repository.load_bookings() == []


def test_live_unmatched_booking_does_not_resolve_to_test_trip_instance(repository: Repository) -> None:
    test_trip = save_trip(
        repository,
        trip_id=None,
        label="Test Scope Trip",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 6),
        anchor_weekday="",
        data_scope="test",
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
    test_trip_instance_id = next(
        item.trip_instance_id for item in snapshot.trip_instances if item.trip_id == test_trip.trip_id
    )
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
            record_locator="LIVE01",
        ),
        data_scope="live",
    )

    assert booking is None
    assert unmatched is not None

    with pytest.raises(KeyError, match="Scheduled trip not found"):
        resolve_unmatched_booking_to_trip_instance(
            repository,
            unmatched_booking_id=unmatched.unmatched_booking_id,
            trip_instance_id=test_trip_instance_id,
        )


def test_unmatched_booking_can_be_resolved_to_a_new_trip(repository: Repository) -> None:
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

    trip = save_trip(
        repository,
        trip_id=None,
        label="Conference Arrival",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SEA",
                "airlines": "Delta",
                "day_offset": 0,
                "start_time": "00:00",
                "end_time": "02:30",
            }
        ],
    )
    snapshot = sync_and_persist(repository, today=date(2026, 5, 1))
    created_booking = resolve_unmatched_booking_to_trip(
        repository,
        unmatched_booking_id=unmatched.unmatched_booking_id,
        trip_id=trip.trip_id,
    )

    assert created_booking is not None
    assert created_booking.record_locator == "ZZZ999"
    assert created_booking.route_option_id != ""
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
    assert moved.candidate_trip_instance_ids == ""
    assert not repository.load_bookings()
    unresolved = next(
        item for item in repository.load_unmatched_bookings() if item.unmatched_booking_id == booking.booking_id
    )
    assert unresolved.candidate_trip_instance_ids == trip_instance_id
    instance = next(item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id)
    assert instance.booking_id == ""


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

    assert saved_booking.trip_instance_id == trip_instance.trip_instance_id
    assert saved_booking.route_option_id != ""
    assert repository.load_unmatched_bookings() == []


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


def test_linked_booking_can_gain_route_match_after_trip_is_updated(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Route Healing Trip",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 6),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SEA",
                "airlines": "Delta",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )
    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance_id = next(item.trip_instance_id for item in snapshot.trip_instances if item.trip_id == trip.trip_id)

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
            record_locator="HEAL01",
        ),
        trip_instance_id=trip_instance_id,
    )

    assert unmatched is None
    assert booking is not None
    assert booking.route_option_id == ""

    save_trip(
        repository,
        trip_id=trip.trip_id,
        label=trip.label,
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 6),
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

    sync_and_persist(repository, today=date(2026, 4, 1))
    refreshed = next(item for item in repository.load_bookings() if item.booking_id == booking.booking_id)

    assert refreshed.route_option_id != ""


def test_linked_booking_route_match_clears_when_trip_route_changes(repository: Repository) -> None:
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
            record_locator="CLEAR01",
        ),
    )

    assert unmatched is None
    assert booking is not None
    assert booking.route_option_id != ""

    trip = next(item for item in repository.load_trips() if item.trip_id == next(
        instance.trip_id
        for instance in repository.load_trip_instances()
        if instance.trip_instance_id == trip_instance_id
    ))
    save_trip(
        repository,
        trip_id=trip.trip_id,
        label=trip.label,
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 6),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SEA",
                "airlines": "Delta",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    sync_and_persist(repository, today=date(2026, 4, 1))
    refreshed = next(item for item in repository.load_bookings() if item.booking_id == booking.booking_id)

    assert refreshed.route_option_id == ""


def test_update_booking_persists_flight_number(repository: Repository) -> None:
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
            record_locator="FLIGHT1",
        ),
        trip_instance_id=trip_instance_id,
    )

    assert booking is not None
    assert unmatched is None

    updated = update_booking(
        repository,
        booking_id=booking.booking_id,
        trip_instance_id=trip_instance_id,
        candidate=BookingCandidate(
            airline="Alaska",
            origin_airport="BUR",
            destination_airport="SFO",
            departure_date=date(2026, 4, 6),
            departure_time="07:15",
            arrival_time="08:40",
            fare_class="basic_economy",
            flight_number="AS 1105",
            booked_price=121,
            record_locator="FLIGHT1",
        ),
    )

    assert updated.flight_number == "AS 1105"
    stored = next(item for item in repository.load_bookings() if item.booking_id == booking.booking_id)
    assert stored.flight_number == "AS 1105"


def test_update_unmatched_booking_persists_flight_number(repository: Repository) -> None:
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
            record_locator="UNFLT1",
        ),
    )

    assert booking is None
    assert unmatched is not None

    updated = update_unmatched_booking(
        repository,
        unmatched_booking_id=unmatched.unmatched_booking_id,
        candidate=BookingCandidate(
            airline="United",
            origin_airport="LAX",
            destination_airport="SFO",
            departure_date=date(2026, 4, 7),
            departure_time="07:15",
            arrival_time="08:40",
            fare_class="basic_economy",
            flight_number="UA 1234",
            booked_price=149,
            record_locator="UNFLT1",
        ),
    )

    assert updated.flight_number == "UA 1234"
    stored = next(
        item for item in repository.load_unmatched_bookings() if item.unmatched_booking_id == unmatched.unmatched_booking_id
    )
    assert stored.flight_number == "UA 1234"
