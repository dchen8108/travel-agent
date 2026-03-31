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
    return persist_programs(repository, programs)


def delete_program(repository: Repository, program_id: str) -> tuple[list[TripInstance], list[Tracker]]:
    existing_trips = repository.load_trip_instances()
    existing_trackers = repository.load_trackers()
    programs = [program for program in repository.load_programs() if program.program_id != program_id]
    trips, trackers = persist_programs(repository, programs)

    removed_trip_ids = {
        trip.trip_instance_id
        for trip in existing_trips
        if trip.program_id == program_id
    }
    removed_tracker_ids = {
        tracker.tracker_id
        for tracker in existing_trackers
        if tracker.trip_instance_id in removed_trip_ids
    }
    if removed_trip_ids or removed_tracker_ids:
        repository.save_bookings(
            [booking for booking in repository.load_bookings() if booking.trip_instance_id not in removed_trip_ids]
        )
        repository.save_fare_observations(
            [
                observation
                for observation in repository.load_fare_observations()
                if observation.trip_instance_id not in removed_trip_ids and observation.tracker_id not in removed_tracker_ids
            ]
        )
        repository.save_review_items(filter_review_items(repository.load_review_items(), removed_tracker_ids))
    return trips, trackers


def persist_programs(repository: Repository, programs: list[Program]) -> tuple[list[TripInstance], list[Tracker]]:
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

    trips_with_trackers, trackers = sync_trackers(
        generated_trips,
        existing_trackers,
        {program.program_id: program for program in active_programs},
    )
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


def filter_review_items(review_items, removed_tracker_ids: set[str]):
    if not removed_tracker_ids:
        return review_items
    filtered = []
    for item in review_items:
        candidate_ids = [candidate for candidate in item.candidate_tracker_ids.split("|") if candidate and candidate not in removed_tracker_ids]
        if item.resolved_tracker_id and item.resolved_tracker_id in removed_tracker_ids:
            continue
        if item.candidate_tracker_ids and not candidate_ids and not item.resolved_tracker_id:
            continue
        item.candidate_tracker_ids = "|".join(candidate_ids)
        filtered.append(item)
    return filtered
