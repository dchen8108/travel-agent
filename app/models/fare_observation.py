from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import CsvModel, SegmentType, utcnow


class FareObservation(CsvModel):
    observation_id: str
    tracker_id: str
    trip_instance_id: str
    segment_type: SegmentType
    source_type: str = "google_flights_email"
    source_id: str
    observed_at: datetime
    airline: str = ""
    fare_type: str = ""
    price: int
    outbound_summary: str = ""
    return_summary: str = ""
    is_best_current_option: bool = False
    created_at: datetime = Field(default_factory=utcnow)
