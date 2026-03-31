from __future__ import annotations

from dataclasses import dataclass

from app.models.booking import Booking
from app.models.email_event import EmailEvent
from app.models.fare_observation import FareObservation
from app.models.program import Program
from app.models.review_item import ReviewItem
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance
from app.models.view_models import DashboardBuckets
from app.services.recommendations import build_dashboard_buckets
from app.services.workflows import recompute_and_persist
from app.storage.repository import Repository


@dataclass
class AppSnapshot:
    programs: list[Program]
    trips: list[TripInstance]
    trackers: list[Tracker]
    bookings: list[Booking]
    observations: list[FareObservation]
    email_events: list[EmailEvent]
    review_items: list[ReviewItem]
    dashboard: DashboardBuckets


def load_snapshot(repository: Repository, recompute: bool = True) -> AppSnapshot:
    repository.ensure_data_dir()
    if recompute:
        recompute_and_persist(repository)

    programs = repository.load_programs()
    trips = repository.load_trip_instances()
    trackers = repository.load_trackers()
    bookings = repository.load_bookings()
    observations = repository.load_fare_observations()
    email_events = repository.load_email_events()
    review_items = repository.load_review_items()
    dashboard = build_dashboard_buckets(trips, trackers, bookings, observations)

    return AppSnapshot(
        programs=programs,
        trips=trips,
        trackers=trackers,
        bookings=bookings,
        observations=observations,
        email_events=email_events,
        review_items=review_items,
        dashboard=dashboard,
    )
