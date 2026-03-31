from __future__ import annotations

from dataclasses import dataclass, field

from app.models.booking import Booking
from app.models.email_event import EmailEvent
from app.models.review_item import ReviewItem
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance


@dataclass
class TripContext:
    trip: TripInstance
    trackers: list[Tracker] = field(default_factory=list)
    best_tracker: Tracker | None = None
    booking: Booking | None = None
    latest_total_price: int | None = None


@dataclass
class DashboardBuckets:
    setup: list[TripContext] = field(default_factory=list)
    action: list[TripContext] = field(default_factory=list)
    booked: list[TripContext] = field(default_factory=list)


@dataclass
class ReviewContext:
    event: EmailEvent
    items: list[ReviewItem]
