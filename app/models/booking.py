from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import BookingStatus, CsvModel, utcnow


class Booking(CsvModel):
    booking_id: str
    trip_instance_id: str
    airline: str = ""
    fare_type: str = ""
    booked_price: int
    booked_at: datetime
    outbound_summary: str = ""
    return_summary: str = ""
    record_locator: str = ""
    status: BookingStatus = BookingStatus.ACTIVE
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
