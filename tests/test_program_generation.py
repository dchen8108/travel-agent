from __future__ import annotations

from datetime import date

from app.models.base import TripMode
from app.models.program import Program
from app.services.programs import generate_trip_instances


def test_generate_trip_instances_creates_round_trip_trackers() -> None:
    program = Program(
        program_id="prog_test",
        program_name="Test commute",
        origin_airports="BUR|LAX",
        destination_airports="SFO",
        outbound_weekday="Monday",
        outbound_time_start="06:00",
        outbound_time_end="10:00",
        return_weekday="Wednesday",
        return_time_start="16:00",
        return_time_end="21:00",
        lookahead_weeks=2,
    )

    trips, trackers = generate_trip_instances(program, today=date(2026, 3, 31))

    assert len(trips) == 4
    assert len(trackers) == 8
    assert trackers[0].google_flights_url.startswith("https://www.google.com/travel/flights?q=")


def test_generate_trip_instances_creates_one_way_trackers() -> None:
    program = Program(
        program_id="prog_oneway",
        program_name="Test outbound",
        trip_mode=TripMode.ONE_WAY,
        origin_airports="BUR|LAX",
        destination_airports="SFO",
        outbound_weekday="Monday",
        outbound_time_start="06:00",
        outbound_time_end="10:00",
        lookahead_weeks=2,
    )

    trips, trackers = generate_trip_instances(program, today=date(2026, 3, 31))

    assert len(trips) == 4
    assert len(trackers) == 4
    assert all(trip.return_date is None for trip in trips)
    assert all(trip.trip_mode == TripMode.ONE_WAY for trip in trips)
