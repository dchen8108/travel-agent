from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.models.base import CsvModel, SegmentType, TrackerStatus, utcnow


class Tracker(CsvModel):
    tracker_id: str
    trip_instance_id: str
    segment_type: SegmentType
    origin_airport: str
    destination_airport: str
    travel_date: date
    provider: str = "google_flights"
    link_source: str = "generated"
    tracking_status: TrackerStatus = TrackerStatus.NEEDS_SETUP
    google_flights_url: str = ""
    tracking_enabled_at: datetime | None = None
    last_signal_at: datetime | None = None
    latest_observed_price: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
