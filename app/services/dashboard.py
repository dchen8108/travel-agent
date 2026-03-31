from __future__ import annotations

from dataclasses import dataclass

from app.models.booking import Booking
from app.models.email_event import EmailEvent
from app.models.fare_observation import FareObservation
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.models.unmatched_booking import UnmatchedBooking
from app.services.recommendations import best_tracker_for_instance
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


@dataclass
class AppSnapshot:
    trips: list[Trip]
    route_options: list[RouteOption]
    trip_instances: list[TripInstance]
    trackers: list[Tracker]
    bookings: list[Booking]
    unmatched_bookings: list[UnmatchedBooking]
    observations: list[FareObservation]
    email_events: list[EmailEvent]


def load_snapshot(repository: Repository, *, recompute: bool = True) -> AppSnapshot:
    repository.ensure_data_dir()
    if recompute:
        return sync_and_persist(repository)
    return AppSnapshot(
        trips=repository.load_trips(),
        route_options=repository.load_route_options(),
        trip_instances=repository.load_trip_instances(),
        trackers=repository.load_trackers(),
        bookings=repository.load_bookings(),
        unmatched_bookings=repository.load_unmatched_bookings(),
        observations=repository.load_fare_observations(),
        email_events=repository.load_email_events(),
    )


def booking_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> Booking | None:
    return next(
        (
            booking
            for booking in snapshot.bookings
            if booking.trip_instance_id == trip_instance_id and booking.status == "active"
        ),
        None,
    )


def route_options_for_trip(snapshot: AppSnapshot, trip_id: str) -> list[RouteOption]:
    return sorted(
        [option for option in snapshot.route_options if option.trip_id == trip_id],
        key=lambda item: item.rank,
    )


def instances_for_trip(snapshot: AppSnapshot, trip_id: str) -> list[TripInstance]:
    return sorted(
        [instance for instance in snapshot.trip_instances if instance.trip_id == trip_id],
        key=lambda item: item.anchor_date,
    )


def trackers_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> list[Tracker]:
    return sorted(
        [tracker for tracker in snapshot.trackers if tracker.trip_instance_id == trip_instance_id],
        key=lambda item: (item.rank, item.travel_date),
    )


def best_tracker(snapshot: AppSnapshot, trip_instance_id: str) -> Tracker | None:
    return best_tracker_for_instance(trackers_for_instance(snapshot, trip_instance_id))
