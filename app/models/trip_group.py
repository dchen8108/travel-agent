from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.models.base import CsvModel, DataScope, utcnow


class TripGroup(CsvModel):
    trip_group_id: str
    label: str
    description: str = ""
    data_scope: DataScope = DataScope.LIVE
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Group name is required.")
        return normalized

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return value.strip()
