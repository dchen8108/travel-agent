from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.models.base import CsvModel, DataScope, TripInstanceGroupMembershipSource, utcnow


class TripInstanceGroupMembership(CsvModel):
    trip_instance_id: str
    trip_group_id: str
    membership_source: TripInstanceGroupMembershipSource = TripInstanceGroupMembershipSource.MANUAL
    source_rule_trip_id: str = ""
    data_scope: DataScope = DataScope.LIVE
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("trip_instance_id", "trip_group_id", "source_rule_trip_id")
    @classmethod
    def normalize_ids(cls, value: str) -> str:
        return value.strip()

    @field_validator("membership_source", mode="before")
    @classmethod
    def normalize_membership_source(cls, value: object) -> object:
        if value in (None, ""):
            return TripInstanceGroupMembershipSource.MANUAL
        return value

    @model_validator(mode="after")
    def validate_membership_source(self) -> "TripInstanceGroupMembership":
        if self.membership_source in {
            TripInstanceGroupMembershipSource.INHERITED,
            TripInstanceGroupMembershipSource.FROZEN,
        }:
            if not self.source_rule_trip_id:
                raise ValueError("Inherited and frozen memberships require a source rule id.")
        elif self.source_rule_trip_id:
            raise ValueError("Manual memberships cannot keep a source rule id.")
        return self
