from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.models.base import CsvModel, TripStatus, utcnow


class TripInstance(CsvModel):
    trip_instance_id: str
    program_id: str
    origin_airport: str
    destination_airport: str
    outbound_date: date
    status: TripStatus = TripStatus.NEEDS_TRACKER_SETUP
    recommendation_reason: str = ""
    best_airline: str = ""
    best_fare_type: str = ""
    best_price: int | None = None
    best_outbound_summary: str = ""
    outbound_tracker_id: str = ""
    last_checked_at: datetime | None = None
    dismissed_until: datetime | None = None
    booking_id: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
