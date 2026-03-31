from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import CsvModel, EmailParsedStatus, utcnow


class EmailEvent(CsvModel):
    email_event_id: str
    provider: str = "google_flights_email"
    source_message_id: str = ""
    received_at: datetime
    subject: str
    parsed_status: EmailParsedStatus
    observation_count: int = 0
    imported_email_path: str
    raw_excerpt: str = ""
    created_at: datetime = Field(default_factory=utcnow)
