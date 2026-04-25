from __future__ import annotations

from datetime import date, datetime

from pydantic import AliasChoices, Field, field_validator

from app.catalog import normalize_airline_code, normalize_airport_code, normalize_stop_value
from app.models.base import CsvModel, DataScope, FareClass, parse_fare_class, utcnow
from app.route_options import join_pipe, split_pipe, validate_time_window


class Tracker(CsvModel):
    tracker_id: str
    trip_instance_id: str
    route_option_id: str
    rank: int
    data_scope: DataScope = DataScope.LIVE
    preference_bias_dollars: int = 0
    origin_airports: str
    destination_airports: str
    airlines: str
    stops: str = "nonstop"
    day_offset: int
    travel_date: date
    start_time: str
    end_time: str
    fare_class: FareClass = Field(
        default=FareClass.BASIC_ECONOMY,
        validation_alias=AliasChoices("fare_class", "fare_class_policy"),
        serialization_alias="fare_class_policy",
    )
    provider: str = "google_flights"
    last_signal_at: datetime | None = None
    latest_observed_price: int | None = None
    latest_fetched_at: datetime | None = None
    latest_winning_origin_airport: str = ""
    latest_winning_destination_airport: str = ""
    latest_signal_source: str = ""
    latest_match_summary: str = ""
    definition_signature: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("origin_airports", "destination_airports")
    @classmethod
    def validate_airport_list(cls, value: str) -> str:
        return join_pipe([normalize_airport_code(item) for item in split_pipe(value)])

    @field_validator("airlines")
    @classmethod
    def validate_airline_list(cls, value: str) -> str:
        return join_pipe([normalize_airline_code(item) for item in split_pipe(value)])

    @field_validator("stops")
    @classmethod
    def validate_stops(cls, value: str) -> str:
        return normalize_stop_value(value)

    @field_validator("rank")
    @classmethod
    def validate_rank(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Tracker rank must be positive.")
        return value

    @field_validator("preference_bias_dollars")
    @classmethod
    def validate_preference_bias_dollars(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Tracker preference bias cannot be negative.")
        return value

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        if value != "google_flights":
            raise ValueError("Only Google Flights is supported in v0.")
        return value

    @field_validator("day_offset")
    @classmethod
    def validate_day_offset(cls, value: int) -> int:
        if value < -1 or value > 1:
            raise ValueError("Choose a supported relative day.")
        return value

    @field_validator("fare_class", mode="before")
    @classmethod
    def validate_fare_class(cls, value: object) -> FareClass:
        return parse_fare_class(value)

    @field_validator("definition_signature")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        return value.strip()

    @field_validator("latest_winning_origin_airport", "latest_winning_destination_airport")
    @classmethod
    def normalize_optional_airport(cls, value: str) -> str:
        value = value.strip()
        return normalize_airport_code(value) if value else ""

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_field(cls, value: str) -> str:
        return value

    @field_validator("latest_observed_price")
    @classmethod
    def validate_latest_price(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("Tracker price cannot be negative.")
        return value

    @field_validator("latest_signal_source")
    @classmethod
    def validate_signal_source(cls, value: str) -> str:
        value = value.strip()
        if value and value != "background_fetch":
            raise ValueError("Unsupported tracker signal source.")
        return value

    @property
    def origin_codes(self) -> list[str]:
        return split_pipe(self.origin_airports)

    @property
    def destination_codes(self) -> list[str]:
        return split_pipe(self.destination_airports)

    @property
    def airline_codes(self) -> list[str]:
        return split_pipe(self.airlines)

    @property
    def primary_origin(self) -> str:
        return self.origin_codes[0]

    @property
    def primary_destination(self) -> str:
        return self.destination_codes[0]

    @field_validator("end_time")
    @classmethod
    def validate_range(cls, value: str, info) -> str:
        start_time = info.data.get("start_time")
        if start_time:
            validate_time_window(start_time, value)
        return value
