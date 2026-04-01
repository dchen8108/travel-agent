from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.catalog import normalize_airport_code
from app.models.base import CsvModel, FetchTargetStatus, utcnow


class TrackerFetchTarget(CsvModel):
    fetch_target_id: str
    tracker_id: str
    trip_instance_id: str
    tracker_definition_signature: str = ""
    origin_airport: str
    destination_airport: str
    schedule_offset_seconds: int = 0
    google_flights_url: str
    last_fetch_started_at: datetime | None = None
    last_fetch_finished_at: datetime | None = None
    last_fetch_status: FetchTargetStatus = FetchTargetStatus.PENDING
    last_fetch_error: str = ""
    consecutive_failures: int = 0
    next_fetch_not_before: datetime | None = None
    latest_price: int | None = None
    latest_airline: str = ""
    latest_departure_label: str = ""
    latest_arrival_label: str = ""
    latest_summary: str = ""
    latest_fetched_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("origin_airport", "destination_airport")
    @classmethod
    def validate_airport(cls, value: str) -> str:
        return normalize_airport_code(value)

    @field_validator("tracker_definition_signature", "google_flights_url", "last_fetch_error", "latest_airline", "latest_departure_label", "latest_arrival_label", "latest_summary")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("consecutive_failures")
    @classmethod
    def validate_failures(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Failure count cannot be negative.")
        return value

    @field_validator("schedule_offset_seconds")
    @classmethod
    def validate_schedule_offset(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Schedule offset cannot be negative.")
        return value

    @field_validator("latest_price")
    @classmethod
    def validate_price(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("Latest price cannot be negative.")
        return value
