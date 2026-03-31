from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

CsvScalar: TypeAlias = str | int | float | bool | date | datetime | None


class CsvModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_empty_values(cls, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        for field_name, field_info in cls.model_fields.items():
            if normalized.get(field_name) is None and field_info.annotation is str:
                normalized[field_name] = ""
        return normalized


class ProgramWeekday(StrEnum):
    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"
    SATURDAY = "Saturday"
    SUNDAY = "Sunday"


class TripStatus(StrEnum):
    NEEDS_TRACKER_SETUP = "needs_tracker_setup"
    NOT_READY = "not_ready"
    WAIT = "wait"
    BOOK_NOW = "book_now"
    BOOKED_MONITORING = "booked_monitoring"
    REBOOK = "rebook"


class TrackerStatus(StrEnum):
    NEEDS_SETUP = "needs_setup"
    TRACKING_ENABLED = "tracking_enabled"
    SIGNAL_RECEIVED = "signal_received"
    STALE = "stale"


class SegmentType(StrEnum):
    OUTBOUND = "outbound"
    RETURN = "return"


class EmailParsedStatus(StrEnum):
    PARSED = "parsed"
    UNMATCHED = "unmatched"
    NEEDS_REVIEW = "needs_review"


class BookingStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    REBOOKED = "rebooked"


class ReviewStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class AppState(CsvModel):
    timezone: str = "America/Los_Angeles"
    default_lookahead_weeks: int = 8
    default_rebook_alert_threshold: int = 20
    email_ingestion_mode: str = "manual_upload"
    version: int = 1


def utcnow() -> datetime:
    return datetime.now().astimezone()
