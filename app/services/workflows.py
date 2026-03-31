from __future__ import annotations

from app.models.base import TrackerStatus
from app.models.booking import Booking
from app.models.fare_observation import FareObservation
from app.models.program import Program
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance
from app.services.recommendations import recompute_trip_states
from app.services.trackers import sync_trackers
from app.services.trip_instances import generate_trip_instances
from app.storage.repository import Repository


def sync_program(repository: Repository, program: Program) -> tuple[list[TripInstance], list[Tracker]]:
    programs = [existing for existing in repository.load_programs() if existing.program_id != program.program_id]
    programs.append(program)
    repository.save_programs(programs)

    active_programs = [item for item in programs if item.active]
    existing_trips = repository.load_trip_instances()
    existing_trackers = repository.load_trackers()
    bookings = repository.load_bookings()
    observations = repository.load_fare_observations()

    generated_trips: list[TripInstance] = []
    for active_program in active_programs:
        prior = [trip for trip in existing_trips if trip.program_id == active_program.program_id]
        generated_trips.extend(generate_trip_instances(active_program, repository.settings, prior))

    trips_with_trackers, trackers = sync_trackers(generated_trips, existing_trackers)
    recomputed_trips = recompute_trip_states(
        trips_with_trackers,
        trackers,
        bookings,
        observations,
        active_programs,
        repository.settings,
    )

    repository.save_trip_instances(recomputed_trips)
    repository.save_trackers(trackers)
    return recomputed_trips, trackers


def recompute_and_persist(repository: Repository) -> tuple[list[TripInstance], list[Tracker]]:
    programs = [program for program in repository.load_programs() if program.active]
    trips = repository.load_trip_instances()
    trackers = repository.load_trackers()
    bookings = repository.load_bookings()
    observations = repository.load_fare_observations()

    refresh_tracker_projections(trackers, observations)
    recomputed_trips = recompute_trip_states(
        trips,
        trackers,
        bookings,
        observations,
        programs,
        repository.settings,
    )
    repository.save_trackers(trackers)
    repository.save_trip_instances(recomputed_trips)
    return recomputed_trips, trackers


def refresh_tracker_projections(
    trackers: list[Tracker],
    observations: list[FareObservation],
) -> list[Tracker]:
    latest_by_tracker: dict[str, FareObservation] = {}
    for observation in observations:
        current = latest_by_tracker.get(observation.tracker_id)
        if current is None:
            latest_by_tracker[observation.tracker_id] = observation
            continue
        if observation.observed_at > current.observed_at:
            latest_by_tracker[observation.tracker_id] = observation
            continue
        if observation.observed_at == current.observed_at and observation.price < current.price:
            latest_by_tracker[observation.tracker_id] = observation

    for tracker in trackers:
        latest = latest_by_tracker.get(tracker.tracker_id)
        if latest is None:
            continue
        tracker.latest_observed_price = latest.price
        tracker.last_signal_at = latest.observed_at
        if tracker.tracking_status == TrackerStatus.NEEDS_SETUP:
            tracker.tracking_status = TrackerStatus.SIGNAL_RECEIVED
        elif tracker.tracking_status in {
            TrackerStatus.TRACKING_ENABLED,
            TrackerStatus.STALE,
        }:
            tracker.tracking_status = TrackerStatus.SIGNAL_RECEIVED
    return trackers
