from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime

from pydantic import Field, field_validator, model_validator

from app.catalog import normalize_airline_code, normalize_airport_code, normalize_stop_value
from app.flight_numbers import join_flight_numbers
from app.money import parse_money
from app.models.base import (
    BookingMatchStatus,
    BookingResolutionStatus,
    BookingStatus,
    CsvModel,
    DataScope,
    FareClass,
    parse_fare_class,
    utcnow,
)
from app.route_options import join_pipe, parse_time, split_pipe


class Booking(CsvModel):
    booking_id: str
    source: str = "manual"
    trip_instance_id: str = ""
    route_option_id: str = ""
    data_scope: DataScope = DataScope.LIVE
    airline: str
    origin_airport: str
    destination_airport: str
    departure_date: date
    departure_time: str
    arrival_time: str = ""
    arrival_day_offset: int = 0
    fare_class: FareClass = FareClass.BASIC_ECONOMY
    stops: str = ""
    flight_number: str = ""
    booked_price: Decimal
    record_locator: str = ""
    booked_at: datetime = Field(default_factory=utcnow)
    status: BookingStatus = BookingStatus.ACTIVE
    match_status: BookingMatchStatus = BookingMatchStatus.MATCHED
    raw_summary: str = ""
    candidate_trip_instance_ids: str = ""
    auto_link_enabled: bool = True
    resolution_status: BookingResolutionStatus = BookingResolutionStatus.RESOLVED
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

    @field_validator("arrival_day_offset")
    @classmethod
    def validate_arrival_day_offset(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Arrival day offset cannot be negative.")
        if value > 7:
            raise ValueError("Arrival day offset is too large.")
        return value

    @field_validator("fare_class", mode="before")
    @classmethod
    def validate_fare_class(cls, value: object) -> FareClass:
        return parse_fare_class(value)

    @field_validator("stops")
    @classmethod
    def normalize_stops(cls, value: str) -> str:
        return normalize_stop_value(value, allow_empty=True)

    @field_validator("flight_number")
    @classmethod
    def normalize_flight_number(cls, value: str) -> str:
        return join_flight_numbers(value)

    @field_validator("record_locator")
    @classmethod
    def normalize_record_locator(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("route_option_id")
    @classmethod
    def normalize_route_option_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("trip_instance_id")
    @classmethod
    def normalize_trip_instance_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("candidate_trip_instance_ids")
    @classmethod
    def normalize_candidates(cls, value: str) -> str:
        return join_pipe(split_pipe(value))

    @field_validator("booked_price")
    @classmethod
    def validate_booked_price(cls, value: object) -> Decimal:
        amount = parse_money(value)
        if amount is None or amount < 0:
            raise ValueError("Booked price must be positive.")
        return amount

    @model_validator(mode="after")
    def validate_chronology(self) -> Booking:
        if not self.arrival_time:
            return self
        departure_minutes = _minutes_since_midnight(self.departure_time)
        arrival_minutes = _minutes_since_midnight(self.arrival_time) + (self.arrival_day_offset * 24 * 60)
        if arrival_minutes <= departure_minutes:
            raise ValueError("Arrival must be after departure. Adjust the arrival day if needed.")
        return self

    @property
    def unmatched_booking_id(self) -> str:
        return self.booking_id

    @property
    def is_linked(self) -> bool:
        return self.match_status == BookingMatchStatus.MATCHED and bool(self.trip_instance_id)

    @property
    def is_unlinked(self) -> bool:
        return self.match_status == BookingMatchStatus.UNMATCHED or not self.trip_instance_id

    @property
    def needs_linking(self) -> bool:
        return self.is_unlinked and self.resolution_status == BookingResolutionStatus.OPEN


def _minutes_since_midnight(value: str) -> int:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute
