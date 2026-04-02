from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.models.base import BookingEmailEventStatus, CsvModel, utcnow
from app.route_options import join_pipe, split_pipe


class BookingEmailEvent(CsvModel):
    email_event_id: str
    gmail_message_id: str
    gmail_thread_id: str = ""
    gmail_history_id: str = ""
    from_address: str = ""
    subject: str = ""
    received_at: datetime = Field(default_factory=utcnow)
    processing_status: BookingEmailEventStatus = BookingEmailEventStatus.IGNORED
    email_kind: str = "unknown"
    extraction_confidence: float = 0.0
    extracted_payload_json: str = ""
    result_booking_ids: str = ""
    result_unmatched_booking_ids: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("gmail_message_id")
    @classmethod
    def validate_message_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("gmail_message_id is required.")
        return value

    @field_validator("result_booking_ids", "result_unmatched_booking_ids")
    @classmethod
    def normalize_id_pipe(cls, value: str) -> str:
        return join_pipe(split_pipe(value))

