from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, field_validator

from app.catalog import normalize_airline_code, normalize_airport_code
from app.models.base import BookingStatus, CsvModel, utcnow
from app.route_options import parse_time


class Booking(CsvModel):
    booking_id: str
    source: str = "manual"
    trip_instance_id: str
    tracker_id: str = ""
    airline: str
    origin_airport: str
    destination_airport: str
    departure_date: date
    departure_time: str
    arrival_time: str = ""
    booked_price: int
    record_locator: str = ""
    booked_at: datetime = Field(default_factory=utcnow)
    status: BookingStatus = BookingStatus.ACTIVE
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("airline")
    @classmethod
    def validate_airline(cls, value: str) -> str:
        return normalize_airline_code(value)

    @field_validator("origin_airport", "destination_airport")
    @classmethod
    def validate_airport(cls, value: str) -> str:
        return normalize_airport_code(value)

    @field_validator("departure_time")
    @classmethod
    def validate_departure_time(cls, value: str) -> str:
        return parse_time(value)

    @field_validator("arrival_time")
    @classmethod
    def validate_arrival_time(cls, value: str) -> str:
        return parse_time(value) if value else ""

    @field_validator("record_locator")
    @classmethod
    def normalize_record_locator(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("booked_price")
    @classmethod
    def validate_booked_price(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Booked price must be positive.")
        return value
