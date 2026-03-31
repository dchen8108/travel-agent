from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models.base import ProgramWeekday
from app.models.program import Program
from app.models.trip_instance import TripInstance
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
) -> list[TripInstance]:
    existing_by_id = {trip.trip_instance_id: trip for trip in (existing_trips or [])}
    start_date = today or datetime.now(ZoneInfo(settings.timezone)).date()
    outbound_dates = next_weekday_dates(start_date, program.outbound_weekday, program.lookahead_weeks)
    trips: list[TripInstance] = []

    origins = split_pipe(program.origin_airports)
    destinations = split_pipe(program.destination_airports)
    for outbound_date in outbound_dates:
        return_date = paired_return_date(outbound_date, program.return_weekday)
        for origin in origins:
            for destination in destinations:
                trip_id = stable_trip_id(program.program_id, origin, destination, outbound_date, return_date)
                prior = existing_by_id.get(trip_id)
                trip = TripInstance(
                    trip_instance_id=trip_id,
                    program_id=program.program_id,
                    origin_airport=origin,
                    destination_airport=destination,
                    outbound_date=outbound_date,
                    return_date=return_date,
                    booking_id=prior.booking_id if prior else "",
                    outbound_tracker_id=prior.outbound_tracker_id if prior else "",
                    return_tracker_id=prior.return_tracker_id if prior else "",
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


def paired_return_date(outbound_date: date, weekday: ProgramWeekday) -> date:
    outbound_weekday = outbound_date.weekday()
    target = WEEKDAY_INDEX[weekday]
    delta = (target - outbound_weekday) % 7
    if delta == 0:
        delta = 7
    return outbound_date + timedelta(days=delta)


def stable_trip_id(
    program_id: str,
    origin: str,
    destination: str,
    outbound_date: date,
    return_date: date,
) -> str:
    return f"trip_{program_id}_{origin}_{destination}_{outbound_date.isoformat()}_{return_date.isoformat()}"


def split_pipe(value: str) -> list[str]:
    return [part for part in value.split("|") if part]
