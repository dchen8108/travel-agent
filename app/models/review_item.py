from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.models.base import CsvModel, ReviewStatus, utcnow


class ReviewItem(CsvModel):
    review_item_id: str
    email_event_id: str
    observed_route: str
    observed_date: date | None = None
    observed_origin_airport: str = ""
    observed_destination_airport: str = ""
    observed_airline: str = ""
    observed_price: int | None = None
    observed_previous_price: int | None = None
    observed_price_direction: str = ""
    observed_time_line: str = ""
    observed_detail_line: str = ""
    observed_flight_url: str = ""
    candidate_tracker_ids: str = ""
    status: ReviewStatus = ReviewStatus.OPEN
    resolution_notes: str = ""
    resolved_tracker_id: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
