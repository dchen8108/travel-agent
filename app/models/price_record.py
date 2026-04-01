from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, field_validator, model_validator

from app.catalog import normalize_airline_code, normalize_airport_code
from app.models.base import CsvModel, utcnow
from app.route_options import join_pipe, split_pipe, validate_time_window


class PriceRecord(CsvModel):
    price_record_id: str
    fetch_event_id: str
    observed_at: datetime
    observed_date: date | None = None
    source: str = "background_fetch"
    provider: str = "google_flights"
    fetch_method: str = "generated_link"
    fetch_target_id: str
    tracker_id: str
    trip_instance_id: str
    trip_id: str
    route_option_id: str
    tracker_definition_signature: str
    trip_label: str = ""
    tracker_rank: int
    search_origin_airports: str
    search_destination_airports: str
    search_airlines: str
    search_day_offset: int
    search_travel_date: date
    search_start_time: str
    search_end_time: str
    query_origin_airport: str
    query_destination_airport: str
    google_flights_url: str = ""
    airline: str
    departure_label: str = ""
    arrival_label: str = ""
    price: int
    price_text: str = ""
    summary: str = ""
    offer_rank: int = 1
    request_offer_count: int = 1
    is_request_cheapest: bool = False
    record_signature: str = ""
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def fill_derived_defaults(self) -> "PriceRecord":
        if self.observed_date is None:
            self.observed_date = self.observed_at.date()
        return self

    @field_validator(
        "trip_label",
        "tracker_definition_signature",
        "google_flights_url",
        "departure_label",
        "arrival_label",
        "price_text",
        "summary",
        "record_signature",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("airline")
    @classmethod
    def validate_airline(cls, value: str) -> str:
        return normalize_airline_code(value)

    @field_validator("search_origin_airports", "search_destination_airports")
    @classmethod
    def validate_airport_lists(cls, value: str) -> str:
        return join_pipe([normalize_airport_code(item) for item in split_pipe(value)])

    @field_validator("query_origin_airport", "query_destination_airport")
    @classmethod
    def validate_airport(cls, value: str) -> str:
        return normalize_airport_code(value)

    @field_validator("search_airlines")
    @classmethod
    def validate_airline_list(cls, value: str) -> str:
        return join_pipe([normalize_airline_code(item) for item in split_pipe(value)])

    @field_validator("tracker_rank")
    @classmethod
    def validate_rank(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Tracker rank must be positive.")
        return value

    @field_validator("search_day_offset")
    @classmethod
    def validate_day_offset(cls, value: int) -> int:
        if value < -1 or value > 1:
            raise ValueError("Choose a supported relative day.")
        return value

    @field_validator("search_end_time")
    @classmethod
    def validate_time_window_end(cls, value: str, info) -> str:
        start_time = info.data.get("search_start_time")
        if start_time:
            validate_time_window(start_time, value)
        return value

    @field_validator("price")
    @classmethod
    def validate_price(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Price record value must be positive.")
        return value

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in {"background_fetch", "manual_import"}:
            raise ValueError("Unsupported price record source.")
        return normalized

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in {"google_flights"}:
            raise ValueError("Unsupported price record provider.")
        return normalized

    @field_validator("fetch_method")
    @classmethod
    def validate_fetch_method(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in {"generated_link", "manual_link"}:
            raise ValueError("Unsupported price record fetch method.")
        return normalized

    @field_validator("offer_rank", "request_offer_count")
    @classmethod
    def validate_positive_counter(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Offer counters must be positive.")
        return value
