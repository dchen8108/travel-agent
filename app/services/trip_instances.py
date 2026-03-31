from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models.base import ProgramWeekday
from app.models.program import Program
from app.models.trip_instance import TripInstance
from app.route_details import parse_route_detail_rankings
from app.settings import Settings

WEEKDAY_INDEX = {
    ProgramWeekday.MONDAY: 0,
    ProgramWeekday.TUESDAY: 1,
    ProgramWeekday.WEDNESDAY: 2,
    ProgramWeekday.THURSDAY: 3,
    ProgramWeekday.FRIDAY: 4,
    ProgramWeekday.SATURDAY: 5,
    ProgramWeekday.SUNDAY: 6,
}


def generate_trip_instances(
    program: Program,
    settings: Settings,
    existing_trips: list[TripInstance] | None = None,
    today: date | None = None,
    lookahead_weeks: int = 12,
) -> list[TripInstance]:
    existing_by_id = {trip.trip_instance_id: trip for trip in (existing_trips or [])}
    start_date = today or datetime.now(ZoneInfo(settings.timezone)).date()
    route_details = parse_route_detail_rankings(program.route_detail_rankings)
    primary_detail = route_details[0]
    anchor_dates = next_weekday_dates(start_date, primary_detail.weekday, lookahead_weeks)
    trips: list[TripInstance] = []

    for anchor_date in anchor_dates:
        trip_id = stable_trip_id(program.program_id, anchor_date)
        prior = existing_by_id.get(trip_id)
        trip = TripInstance(
            trip_instance_id=trip_id,
            program_id=program.program_id,
            origin_airport=primary_detail.origin_airport,
            destination_airport=primary_detail.destination_airport,
            outbound_date=anchor_date,
            booking_id=prior.booking_id if prior else "",
            outbound_tracker_id=prior.outbound_tracker_id if prior else "",
            dismissed_until=prior.dismissed_until if prior else None,
            created_at=prior.created_at if prior else datetime.now().astimezone(),
        )
        if prior is not None:
            trip.updated_at = prior.updated_at
        trips.append(trip)
    return trips


def next_weekday_dates(start: date, weekday: ProgramWeekday, count: int) -> list[date]:
    target = WEEKDAY_INDEX[weekday]
    delta = (target - start.weekday()) % 7
    first = start + timedelta(days=delta)
    return [first + timedelta(days=7 * offset) for offset in range(count)]


def detail_date_from_anchor(anchor_date: date, primary_weekday: ProgramWeekday, detail_weekday: ProgramWeekday) -> date:
    primary_index = WEEKDAY_INDEX[primary_weekday]
    detail_index = WEEKDAY_INDEX[detail_weekday]
    return anchor_date + timedelta(days=detail_index - primary_index)


def stable_trip_id(program_id: str, anchor_date: date) -> str:
    return f"trip_{program_id}_{anchor_date.isoformat()}_oneway"
