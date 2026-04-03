from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, field_validator, model_validator

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
    travel_state: TravelState = TravelState.ACTIVE
    booking_id: str = ""
    last_signal_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("travel_state", mode="before")
    @classmethod
    def normalize_travel_state(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"planned", "booked", "open", "active", ""}:
                return TravelState.ACTIVE
            if normalized == "skipped":
                return TravelState.SKIPPED
        return value

    @model_validator(mode="after")
    def validate_rule_linkage(self) -> "TripInstance":
        if self.instance_kind == TripInstanceKind.STANDALONE:
            if self.inheritance_mode == TripInstanceInheritanceMode.MANUAL:
                if self.recurring_rule_trip_id or self.rule_occurrence_date is not None:
                    raise ValueError("Manual standalone trip instances cannot keep recurring rule linkage.")
                return self
            if self.inheritance_mode != TripInstanceInheritanceMode.DETACHED:
                raise ValueError("Standalone trip instances must be manual or detached.")
            if not self.recurring_rule_trip_id or self.rule_occurrence_date is None:
                raise ValueError("Detached standalone trip instances require recurring rule linkage.")
            return self

        if self.inheritance_mode != TripInstanceInheritanceMode.ATTACHED:
            raise ValueError("Generated trip instances must remain attached to their recurring rule.")

        if not self.recurring_rule_trip_id or self.rule_occurrence_date is None:
            raise ValueError("Attached and detached generated instances require recurring rule linkage.")
        return self
