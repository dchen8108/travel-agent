from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from app.catalog import SUPPORTED_AIRLINES, booking_fare_values
from app.models.base import BookingStatus
from app.models.booking import Booking
from app.models.trip_instance import TripInstance
from app.services.ids import new_id


def upsert_booking(
    bookings: list[Booking],
    trip: TripInstance,
    form: Mapping[str, str],
) -> tuple[list[Booking], Booking]:
    now = datetime.now().astimezone()
    existing = next((booking for booking in bookings if booking.trip_instance_id == trip.trip_instance_id and booking.status == BookingStatus.ACTIVE), None)
    booking = Booking(
        booking_id=existing.booking_id if existing else new_id("book"),
        trip_instance_id=trip.trip_instance_id,
        tracker_id=form.get("tracker_id", "").strip(),
        airline=normalize_airline(form.get("airline", "").strip()),
        fare_type=normalize_fare_type(form.get("fare_type", "").strip()),
        booked_price=int(form.get("booked_price", "0") or 0),
        booked_at=parse_datetime_input(form.get("booked_at", "")) or now,
        outbound_summary=form.get("outbound_summary", "").strip(),
        record_locator=form.get("record_locator", "").strip(),
        status=BookingStatus.ACTIVE,
        notes=form.get("notes", "").strip(),
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    updated = [item for item in bookings if item.booking_id != booking.booking_id]
    updated.append(booking)
    trip.booking_id = booking.booking_id
    return updated, booking


def parse_datetime_input(value: str) -> datetime | None:
    if not value:
        return None
    try:
        naive = datetime.fromisoformat(value)
    except ValueError:
        return None
    return naive.astimezone() if naive.tzinfo else naive.astimezone()


def normalize_airline(value: str) -> str:
    if not value:
        return ""
    lookup = {item["code"].lower(): item["code"] for item in SUPPORTED_AIRLINES}
    return lookup.get(value.lower(), value)


def normalize_fare_type(value: str) -> str:
    if not value:
        return "Flexible"
    lookup = {item.lower(): item for item in booking_fare_values()}
    return lookup.get(value.lower(), value)
