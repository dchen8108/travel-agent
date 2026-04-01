from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, model_validator

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
            if field_name not in normalized:
                continue
            if normalized[field_name] is None and field_info.annotation is str:
                normalized[field_name] = ""
            elif normalized[field_name] == "" and field_info.annotation is str:
                normalized[field_name] = ""
        return normalized


class TripKind(StrEnum):
    ONE_TIME = "one_time"
    WEEKLY = "weekly"


class TripInstanceKind(StrEnum):
    STANDALONE = "standalone"
    GENERATED = "generated"


class TravelState(StrEnum):
    OPEN = "open"
    BOOKED = "booked"
    SKIPPED = "skipped"


class RecommendationState(StrEnum):
    NEEDS_TRACKER_SETUP = "needs_tracker_setup"
    WAIT = "wait"
    BOOK_NOW = "book_now"
    BOOKED_MONITORING = "booked_monitoring"
    REBOOK = "rebook"


class TrackerStatus(StrEnum):
    NEEDS_SETUP = "needs_setup"
    TRACKING_ENABLED = "tracking_enabled"
    SIGNAL_RECEIVED = "signal_received"
    STALE = "stale"


class FetchTargetStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    NO_RESULTS = "no_results"
    NO_WINDOW_MATCH = "no_window_match"
    FAILED = "failed"


class BookingStatus(StrEnum):
    ACTIVE = "active"
    REBOOKED = "rebooked"


class UnmatchedBookingStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class AppState(CsvModel):
    timezone: str = "America/Los_Angeles"
    future_weeks: int = 12
    enable_background_fetcher: bool = True
    version: int = 4


def utcnow() -> datetime:
    return datetime.now().astimezone()
