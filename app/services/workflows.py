from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.models.booking import Booking
from app.models.email_event import EmailEvent
from app.models.fare_observation import FareObservation
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.models.unmatched_booking import UnmatchedBooking
from app.route_options import join_pipe, split_pipe
from app.services.fetch_targets import reconcile_fetch_targets
from app.services.recommendations import (
    apply_fetch_target_rollups,
    recompute_trip_states,
    refresh_tracker_projections,
)
from app.services.trackers import reconcile_trackers
from app.services.trip_instances import reconcile_trip_instances
from app.storage.repository import Repository


@dataclass
class WorkflowSnapshot:
    trips: list[Trip]
    route_options: list[RouteOption]
    trip_instances: list[TripInstance]
    trackers: list[Tracker]
    tracker_fetch_targets: list[TrackerFetchTarget]
    bookings: list[Booking]
    unmatched_bookings: list[UnmatchedBooking]
    observations: list[FareObservation]
    email_events: list[EmailEvent]
    app_state: object


def _filter_candidate_trip_ids(value: str, valid_ids: set[str]) -> str:
    return join_pipe([item for item in split_pipe(value) if item in valid_ids])


def sync_and_persist(repository: Repository, *, today: date | None = None) -> WorkflowSnapshot:
    repository.ensure_data_dir()
    today = today or date.today()

    app_state = repository.load_app_state()
    trips = repository.load_trips()
    route_options = repository.load_route_options()
    existing_trip_instances = repository.load_trip_instances()
    existing_trackers = repository.load_trackers()
    existing_fetch_targets = repository.load_tracker_fetch_targets()
    bookings = repository.load_bookings()
    unmatched_bookings = repository.load_unmatched_bookings()
    observations = repository.load_fare_observations()
    email_events = repository.load_email_events()

    trip_instances = reconcile_trip_instances(
        trips,
        existing_trip_instances,
        today=today,
        future_weeks=app_state.future_weeks,
    )
    trackers = reconcile_trackers(trip_instances, route_options, existing_trackers, today=today)
    tracker_fetch_targets = reconcile_fetch_targets(trackers, existing_fetch_targets)

    valid_trip_instance_ids = {item.trip_instance_id for item in trip_instances}
    valid_tracker_ids = {item.tracker_id for item in trackers}

    filtered_bookings: list[Booking] = []
    for booking in bookings:
        if booking.trip_instance_id not in valid_trip_instance_ids:
            continue
        if booking.tracker_id and booking.tracker_id not in valid_tracker_ids:
            booking.tracker_id = ""
        filtered_bookings.append(booking)
    bookings = filtered_bookings
    observations = [
        observation
        for observation in observations
        if observation.trip_instance_id in valid_trip_instance_ids and observation.tracker_id in valid_tracker_ids
    ]
    for unmatched in unmatched_bookings:
        unmatched.candidate_trip_instance_ids = _filter_candidate_trip_ids(
            unmatched.candidate_trip_instance_ids,
            valid_trip_instance_ids,
        )

    refresh_tracker_projections(trackers, observations)
    apply_fetch_target_rollups(trackers, tracker_fetch_targets)
    recompute_trip_states(trip_instances, trackers, bookings, observations)

    repository.save_trip_instances(trip_instances)
    repository.save_trackers(trackers)
    repository.save_tracker_fetch_targets(tracker_fetch_targets)
    repository.save_bookings(bookings)
    repository.save_unmatched_bookings(unmatched_bookings)
    repository.save_fare_observations(observations)

    return WorkflowSnapshot(
        trips=trips,
        route_options=route_options,
        trip_instances=trip_instances,
        trackers=trackers,
        tracker_fetch_targets=tracker_fetch_targets,
        bookings=bookings,
        unmatched_bookings=unmatched_bookings,
        observations=observations,
        email_events=email_events,
        app_state=app_state,
    )
