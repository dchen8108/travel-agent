from __future__ import annotations

from datetime import date, datetime

from pydantic import AliasChoices, Field, field_validator

from app.catalog import normalize_airline_code, normalize_airport_code, normalize_stop_value
from app.models.base import CsvModel, DataScope, FareClass, parse_fare_class
from app.route_options import join_pipe, split_pipe, validate_time_window


class PriceRecord(CsvModel):
    price_record_id: str
    fetch_event_id: str
    observed_at: datetime
    data_scope: DataScope = DataScope.LIVE
    fetch_target_id: str
    tracker_id: str
    trip_instance_id: str
    trip_id: str
    route_option_id: str
    tracker_definition_signature: str
    tracker_rank: int
    search_origin_airports: str
    search_destination_airports: str
    search_airlines: str
    search_day_offset: int
    search_travel_date: date
    search_start_time: str
    search_end_time: str
    search_fare_class: FareClass = Field(
        default=FareClass.BASIC_ECONOMY,
        validation_alias=AliasChoices("search_fare_class", "search_fare_class_policy"),
        serialization_alias="search_fare_class_policy",
    )
    search_stops: str = Field(
        default="nonstop",
        validation_alias=AliasChoices("search_stops", "search_stops_policy"),
        serialization_alias="search_stops_policy",
    )
    query_origin_airport: str
    query_destination_airport: str
    airline: str
    departure_label: str = ""
    arrival_label: str = ""
    stops: str = ""
    price: int
    offer_rank: int = 1

    @field_validator(
        "tracker_definition_signature",
        "departure_label",
        "arrival_label",
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

    @field_validator("search_fare_class", mode="before")
    @classmethod
    def validate_search_fare_class(cls, value: object) -> FareClass:
        return parse_fare_class(value)

    @field_validator("search_stops")
    @classmethod
    def validate_search_stops(cls, value: str) -> str:
        return normalize_stop_value(value)

    @field_validator("stops")
    @classmethod
    def validate_stops(cls, value: str) -> str:
        return normalize_stop_value(value, allow_empty=True)

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

    @field_validator("offer_rank")
    @classmethod
    def validate_positive_counter(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Offer counters must be positive.")
        return value
