from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.models.base import CsvModel, RecommendationState, TravelState, TripInstanceKind, utcnow


class TripInstance(CsvModel):
    trip_instance_id: str
    trip_id: str
    display_label: str
    anchor_date: date
    instance_kind: TripInstanceKind = TripInstanceKind.STANDALONE
    travel_state: TravelState = TravelState.OPEN
    recommendation_state: RecommendationState = RecommendationState.NEEDS_TRACKER_SETUP
    recommendation_reason: str = ""
    booking_id: str = ""
    last_signal_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
