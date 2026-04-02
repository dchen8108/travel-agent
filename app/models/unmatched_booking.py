from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime

from pydantic import Field, field_validator

from app.catalog import normalize_airline_code, normalize_airport_code
from app.money import parse_money
from app.models.base import CsvModel, DataScope, UnmatchedBookingStatus, utcnow
from app.route_options import join_pipe, parse_time, split_pipe


class UnmatchedBooking(CsvModel):
    unmatched_booking_id: str
    source: str = "manual"
    data_scope: DataScope = DataScope.LIVE
    airline: str
    origin_airport: str
    destination_airport: str
    departure_date: date
    departure_time: str
    arrival_time: str = ""
    booked_price: Decimal
    record_locator: str = ""
    raw_summary: str = ""
    candidate_trip_instance_ids: str = ""
    auto_link_enabled: bool = True
    resolution_status: UnmatchedBookingStatus = UnmatchedBookingStatus.OPEN
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

    @field_validator("candidate_trip_instance_ids")
    @classmethod
    def normalize_candidates(cls, value: str) -> str:
        return join_pipe(split_pipe(value))

    @field_validator("booked_price")
    @classmethod
    def validate_price(cls, value: object) -> Decimal:
        amount = parse_money(value)
        if amount is None or amount < 0:
            raise ValueError("Booked price must be positive.")
        return amount
