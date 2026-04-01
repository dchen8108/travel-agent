from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.catalog import normalize_airline_code, normalize_airport_code
from app.models.base import CsvModel, utcnow
from app.route_options import join_pipe, split_pipe, validate_time_window


class RouteOption(CsvModel):
    route_option_id: str
    trip_id: str
    rank: int
    savings_needed_vs_previous: int = 0
    origin_airports: str
    destination_airports: str
    airlines: str
    day_offset: int
    start_time: str
    end_time: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("rank")
    @classmethod
    def validate_rank(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Route option rank must be positive.")
        return value

    @field_validator("savings_needed_vs_previous")
    @classmethod
    def validate_savings_needed_vs_previous(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Savings threshold must be zero or greater.")
        return value

    @field_validator("origin_airports", "destination_airports")
    @classmethod
    def validate_airport_list(cls, value: str) -> str:
        normalized = [normalize_airport_code(item) for item in split_pipe(value)]
        if not normalized:
            raise ValueError("Choose at least one airport.")
        if len(normalized) > 3:
            raise ValueError("Choose at most three airports.")
        return join_pipe(normalized)

    @field_validator("airlines")
    @classmethod
    def validate_airline_list(cls, value: str) -> str:
        normalized = [normalize_airline_code(item) for item in split_pipe(value)]
        if not normalized:
            raise ValueError("Choose at least one airline.")
        return join_pipe(normalized)

    @field_validator("day_offset")
    @classmethod
    def validate_day_offset(cls, value: int) -> int:
        if value < -1 or value > 1:
            raise ValueError("Choose a supported relative day.")
        return value

    @model_validator(mode="after")
    def validate_times(self) -> "RouteOption":
        self.start_time, self.end_time = validate_time_window(self.start_time, self.end_time)
        return self

    @property
    def origin_codes(self) -> list[str]:
        return split_pipe(self.origin_airports)

    @property
    def destination_codes(self) -> list[str]:
        return split_pipe(self.destination_airports)

    @property
    def airline_codes(self) -> list[str]:
        return split_pipe(self.airlines)
