from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

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


def is_past_instance(instance: TripInstance, *, today: date | None = None) -> bool:
    today = today or date.today()
    return instance.anchor_date < today


def horizon_instances_for_trip(snapshot: AppSnapshot, trip_id: str, *, today: date | None = None) -> list[TripInstance]:
    today = today or date.today()
    return [instance for instance in instances_for_trip(snapshot, trip_id) if not is_past_instance(instance, today=today)]


def past_instances_for_trip(snapshot: AppSnapshot, trip_id: str, *, today: date | None = None) -> list[TripInstance]:
    today = today or date.today()
    return [instance for instance in instances_for_trip(snapshot, trip_id) if is_past_instance(instance, today=today)]


def trackers_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> list[Tracker]:
    return sorted(
        [tracker for tracker in snapshot.trackers if tracker.trip_instance_id == trip_instance_id],
        key=lambda item: (item.rank, item.travel_date),
    )


def best_tracker(snapshot: AppSnapshot, trip_instance_id: str) -> Tracker | None:
    return best_tracker_for_instance(trackers_for_instance(snapshot, trip_instance_id))


def trip_for_instance(snapshot: AppSnapshot, trip_instance_id: str) -> Trip | None:
    instance = next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)
    if instance is None:
        return None
    return next((trip for trip in snapshot.trips if trip.trip_id == instance.trip_id), None)


def trip_focus_url(
    snapshot: AppSnapshot,
    trip_id: str,
    *,
    trip_instance_id: str | None = None,
    show_skipped: bool | None = None,
) -> str:
    trip = next((item for item in snapshot.trips if item.trip_id == trip_id), None)
    if trip is None:
        return "/trips"

    trip_instance = (
        next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)
        if trip_instance_id
        else None
    )
    if show_skipped is None and trip_instance is not None:
        show_skipped = trip_instance.travel_state == "skipped"

    params: list[tuple[str, str]] = []
    anchor = ""
    if trip.trip_kind == "weekly":
        params.append(("recurring_trip_id", trip.trip_id))
        anchor = f"recurring-{trip.trip_id}"
    else:
        params.append(("q", trip.label))
    if show_skipped:
        params.append(("show_skipped", "true"))
    if trip_instance_id:
        anchor = f"{'past' if trip_instance and is_past_instance(trip_instance) else 'scheduled'}-{trip_instance_id}"

    query = urlencode(params, doseq=True)
    url = "/trips"
    if query:
        url = f"{url}?{query}"
    if anchor:
        url = f"{url}#{anchor}"
    return url


def recurring_trips(snapshot: AppSnapshot) -> list[Trip]:
    return sorted(
        [trip for trip in snapshot.trips if trip.trip_kind == "weekly"],
        key=lambda item: item.label.lower(),
    )


def scheduled_instances(
    snapshot: AppSnapshot,
    *,
    include_skipped: bool = False,
    recurring_trip_ids: set[str] | None = None,
    today: date | None = None,
) -> list[TripInstance]:
    today = today or date.today()
    items = [item for item in snapshot.trip_instances if not is_past_instance(item, today=today)]
    if not include_skipped:
        items = [item for item in items if item.travel_state != "skipped"]
    if recurring_trip_ids:
        items = [item for item in items if item.trip_id in recurring_trip_ids]
    return sorted(
        items,
        key=lambda item: (item.anchor_date, item.display_label.lower()),
    )


def past_instances(
    snapshot: AppSnapshot,
    *,
    include_skipped: bool = False,
    recurring_trip_ids: set[str] | None = None,
    today: date | None = None,
) -> list[TripInstance]:
    today = today or date.today()
    items = [item for item in snapshot.trip_instances if is_past_instance(item, today=today)]
    if not include_skipped:
        items = [item for item in items if item.travel_state != "skipped"]
    if recurring_trip_ids:
        items = [item for item in items if item.trip_id in recurring_trip_ids]
    return sorted(
        items,
        key=lambda item: (item.anchor_date, item.display_label.lower()),
        reverse=True,
    )
