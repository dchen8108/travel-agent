from __future__ import annotations

from datetime import date

from app.models.program import Program
from app.services.programs import generate_trip_instances
from app.time_slots import RankedTimeSlot, serialize_time_slot_rankings


def test_generate_trip_instances_creates_ranked_slot_trackers() -> None:
    program = Program(
        program_id="prog_test",
        program_name="Test commute",
        origin_airports="BUR|LAX",
        destination_airports="SFO",
        time_slot_rankings=serialize_time_slot_rankings(
            [
                RankedTimeSlot(weekday="Monday", start_time="06:00", end_time="10:00"),
                RankedTimeSlot(weekday="Sunday", start_time="18:00", end_time="21:00"),
            ]
        ),
        lookahead_weeks=2,
    )

    trips, trackers = generate_trip_instances(program, today=date(2026, 3, 31))

    assert len(trips) == 4
    assert len(trackers) == 8
    assert {tracker.slot_rank for tracker in trackers} == {1, 2}
    assert trackers[0].google_flights_url.startswith("https://www.google.com/travel/flights?q=")


def test_generate_trip_instances_skips_ranked_slots_that_are_already_past() -> None:
    program = Program(
        program_id="prog_test",
        program_name="Midweek fallback",
        origin_airports="BUR",
        destination_airports="SFO",
        time_slot_rankings=serialize_time_slot_rankings(
            [
                RankedTimeSlot(weekday="Wednesday", start_time="06:00", end_time="10:00"),
                RankedTimeSlot(weekday="Monday", start_time="18:00", end_time="21:00"),
            ]
        ),
        lookahead_weeks=1,
    )

    trips, trackers = generate_trip_instances(program, today=date(2026, 4, 7))

    assert len(trips) == 1
    assert len(trackers) == 1
    assert trackers[0].travel_date == date(2026, 4, 8)
