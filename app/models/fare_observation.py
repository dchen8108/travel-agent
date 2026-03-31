from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, field_validator

from app.catalog import normalize_airline_code, normalize_airport_code
from app.models.base import CsvModel, utcnow
from app.route_options import parse_time


class FareObservation(CsvModel):
    fare_observation_id: str
    email_event_id: str
    tracker_id: str
    trip_instance_id: str
    observed_at: datetime
    airline: str
    origin_airport: str
    destination_airport: str
    travel_date: date
    departure_time: str
    arrival_time: str = ""
    price: int
    previous_price: int | None = None
    price_direction: str = ""
    match_summary: str = ""
    created_at: datetime = Field(default_factory=utcnow)

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

    @field_validator("price")
    @classmethod
    def validate_price(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Observation price must be positive.")
        return value
