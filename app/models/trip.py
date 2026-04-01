from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, field_validator, model_validator

from app.catalog import WEEKDAYS
from app.models.base import CsvModel, RoutePreferenceMode, TripKind, utcnow


class Trip(CsvModel):
    trip_id: str
    label: str
    trip_kind: TripKind
    preference_mode: RoutePreferenceMode = RoutePreferenceMode.EQUAL
    active: bool = True
    anchor_date: date | None = None
    anchor_weekday: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Trip label is required.")
        return normalized

    @field_validator("anchor_weekday")
    @classmethod
    def validate_anchor_weekday(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and normalized not in WEEKDAYS:
            raise ValueError("Choose a supported weekday.")
        return normalized

    @field_validator("preference_mode")
    @classmethod
    def validate_preference_mode(cls, value: RoutePreferenceMode) -> RoutePreferenceMode:
        return value

    @model_validator(mode="after")
    def validate_schedule(self) -> "Trip":
        if self.trip_kind == TripKind.ONE_TIME:
            if self.anchor_date is None:
                raise ValueError("One-time trips require an anchor date.")
            self.anchor_weekday = ""
        elif self.trip_kind == TripKind.WEEKLY:
            if not self.anchor_weekday:
                raise ValueError("Weekly trips require an anchor weekday.")
            self.anchor_date = None
        return self

    @property
    def effective_anchor_weekday(self) -> str:
        if self.trip_kind == TripKind.ONE_TIME and self.anchor_date is not None:
            return self.anchor_date.strftime("%A")
        return self.anchor_weekday
