from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.models.base import CsvModel, EmailParsedStatus, utcnow


class EmailEvent(CsvModel):
    email_event_id: str
    provider: str = "google_flights"
    source_message_id: str = ""
    received_at: datetime
    subject: str
    parsed_status: EmailParsedStatus
    observation_count: int = 0
    matched_observation_count: int = 0
    imported_email_path: str = ""
    raw_excerpt: str = ""
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        if value != "google_flights":
            raise ValueError("Only Google Flights is supported in v0.")
        return value
