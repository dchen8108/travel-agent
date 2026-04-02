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


class RoutePreferenceMode(StrEnum):
    EQUAL = "equal"
    RANKED_BIAS = "ranked_bias"


class FareClassPolicy(StrEnum):
    INCLUDE_BASIC = "include_basic"
    EXCLUDE_BASIC = "exclude_basic"


class TripInstanceKind(StrEnum):
    STANDALONE = "standalone"
    GENERATED = "generated"


class TripInstanceInheritanceMode(StrEnum):
    MANUAL = "manual"
    ATTACHED = "attached"
    DETACHED = "detached"


class TripInstanceGroupMembershipSource(StrEnum):
    MANUAL = "manual"
    INHERITED = "inherited"
    FROZEN = "frozen"


class TravelState(StrEnum):
    PLANNED = "planned"
    BOOKED = "booked"
    SKIPPED = "skipped"

class FetchTargetStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    NO_RESULTS = "no_results"
    NO_WINDOW_MATCH = "no_window_match"
    FAILED = "failed"


class BookingStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class UnmatchedBookingStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class BookingEmailEventStatus(StrEnum):
    IGNORED = "ignored"
    RESOLVED_AUTO = "resolved_auto"
    NEEDS_RESOLUTION = "needs_resolution"
    DUPLICATE = "duplicate"
    ERROR = "error"


class DataScope(StrEnum):
    LIVE = "live"
    TEST = "test"


class AppState(CsvModel):
    timezone: str = "America/Los_Angeles"
    future_weeks: int = 16
    enable_background_fetcher: bool = True
    show_test_data: bool = False
    process_test_data: bool = False
    version: int = 5


def utcnow() -> datetime:
    return datetime.now().astimezone()
