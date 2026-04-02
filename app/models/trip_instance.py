from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.models.base import (
    CsvModel,
    DataScope,
    TravelState,
    TripInstanceInheritanceMode,
    TripInstanceKind,
    utcnow,
)


class TripInstance(CsvModel):
    trip_instance_id: str
    trip_id: str
    display_label: str
    anchor_date: date
    data_scope: DataScope = DataScope.LIVE
    instance_kind: TripInstanceKind = TripInstanceKind.STANDALONE
    recurring_rule_trip_id: str = ""
    rule_occurrence_date: date | None = None
    inheritance_mode: TripInstanceInheritanceMode = TripInstanceInheritanceMode.MANUAL
    deleted: bool = False
    travel_state: TravelState = TravelState.PLANNED
    booking_id: str = ""
    last_signal_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
