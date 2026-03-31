from __future__ import annotations

from datetime import date

from app.models.program import Program
from app.route_details import RankedRouteDetail, serialize_route_detail_rankings
from app.services.programs import generate_trip_instances


def route_details_json(*details: RankedRouteDetail) -> str:
    return serialize_route_detail_rankings(list(details))


def test_generate_trip_instances_creates_ranked_route_trackers() -> None:
    program = Program(
        program_id="prog_test",
        program_name="Test commute",
        route_detail_rankings=route_details_json(
            RankedRouteDetail(
                origin_airport="BUR",
                destination_airport="SFO",
                weekday="Monday",
                start_time="06:00",
                end_time="10:00",
                airline="Alaska",
                nonstop_only=True,
            ),
            RankedRouteDetail(
                origin_airport="LAX",
                destination_airport="SFO",
                weekday="Sunday",
                start_time="18:00",
                end_time="21:00",
                airline="United",
                nonstop_only=True,
            ),
        ),
    )

    trips, trackers = generate_trip_instances(program, today=date(2026, 3, 31))

    assert len(trips) == 12
    assert len(trackers) == 24
    assert {tracker.detail_rank for tracker in trackers} == {1, 2}
    assert trackers[0].google_flights_url.startswith("https://www.google.com/travel/flights?q=")


def test_generate_trip_instances_skips_route_details_that_are_already_past() -> None:
    program = Program(
        program_id="prog_test",
        program_name="Midweek fallback",
        route_detail_rankings=route_details_json(
            RankedRouteDetail(
                origin_airport="BUR",
                destination_airport="SFO",
                weekday="Wednesday",
                start_time="06:00",
                end_time="10:00",
                airline="Alaska",
                nonstop_only=True,
            ),
            RankedRouteDetail(
                origin_airport="BUR",
                destination_airport="SFO",
                weekday="Monday",
                start_time="18:00",
                end_time="21:00",
                airline="Alaska",
                nonstop_only=True,
            ),
        ),
    )

    trips, trackers = generate_trip_instances(program, today=date(2026, 4, 7))

    assert len(trips) == 12
    first_week_trackers = [tracker for tracker in trackers if tracker.travel_date <= date(2026, 4, 8)]
    assert len(first_week_trackers) == 1
    assert first_week_trackers[0].travel_date == date(2026, 4, 8)
