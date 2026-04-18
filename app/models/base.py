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


class FareClass(StrEnum):
    BASIC_ECONOMY = "basic_economy"
    ECONOMY = "economy"


class FareClassPolicy(StrEnum):
    INCLUDE_BASIC = "include_basic"
    EXCLUDE_BASIC = "exclude_basic"


def parse_fare_class(value: object, *, default: FareClass = FareClass.ECONOMY) -> FareClass:
    if isinstance(value, FareClass):
        return value
    if isinstance(value, FareClassPolicy):
        return FareClass.BASIC_ECONOMY if value == FareClassPolicy.INCLUDE_BASIC else FareClass.ECONOMY
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    if raw in {FareClass.BASIC_ECONOMY, "basic", FareClassPolicy.INCLUDE_BASIC}:
        return FareClass.BASIC_ECONOMY
    if raw in {FareClass.ECONOMY, "main", "unknown", FareClassPolicy.EXCLUDE_BASIC}:
        return FareClass.ECONOMY
    raise ValueError("Choose a supported fare.")


def fare_class_label(value: object) -> str:
    fare_class = parse_fare_class(value)
    if fare_class == FareClass.BASIC_ECONOMY:
        return "Basic Economy"
    return "Economy"


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


class FetchTargetStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    NO_RESULTS = "no_results"
    NO_WINDOW_MATCH = "no_window_match"
    FAILED = "failed"


class BookingStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class BookingMatchStatus(StrEnum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"


class BookingResolutionStatus(StrEnum):
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
    dashboard_needs_booking_window_weeks: int = Field(default=6, ge=1)
    dashboard_overbooked_window_days: int = Field(default=7, ge=1)
    tracker_freshness_window_hours: int = Field(default=72, ge=1)
    fetch_stagger_seconds: int = Field(default=10, ge=0)
    fetch_max_targets_per_run: int = Field(default=3, ge=0)
    fetch_claim_lease_minutes: int = Field(default=15, ge=1)
    fetch_request_timeout_seconds: float = Field(default=20.0, gt=0)
    fetch_request_sleep_max_extra_seconds: float = Field(default=3.0, ge=0)
    fetch_failure_backoff_hours_first: int = Field(default=12, ge=1)
    fetch_failure_backoff_hours_second: int = Field(default=24, ge=1)
    fetch_failure_backoff_hours_repeated: int = Field(default=48, ge=1)
    fetch_startup_jitter_seconds: float = Field(default=8.0, ge=0)
    launchd_fetch_interval_seconds: int = Field(default=60, ge=1)
    launchd_fetch_max_targets: int = Field(default=2, ge=0)
    show_test_data: bool = False
    process_test_data: bool = False
    version: int = 6


def utcnow() -> datetime:
    return datetime.now().astimezone()
