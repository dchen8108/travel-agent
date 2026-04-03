from __future__ import annotations

from datetime import date

from app.models.base import utcnow
from app.models.booking import Booking
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.route_options import join_pipe, split_pipe
from app.services.bookings import reconcile_booking_route_options, reconcile_unmatched_bookings
from app.services.fetch_targets import reconcile_fetch_targets
from app.services.group_memberships import reconcile_trip_instance_group_memberships
from app.services.recommendations import apply_fetch_target_rollups, recompute_trip_states
from app.services.snapshots import AppSnapshot
from app.services.trackers import reconcile_trackers
from app.services.trip_instances import reconcile_trip_instances
from app.storage.repository import Repository


def _filter_candidate_trip_ids(value: str, valid_ids: set[str]) -> str:
    return join_pipe([item for item in split_pipe(value) if item in valid_ids])


def _preserve_active_fetch_claims(
    tracker_fetch_targets: list[TrackerFetchTarget],
    current_fetch_targets: list[TrackerFetchTarget],
) -> None:
    # Claims are operational concurrency guards. Keep any live claim already in the
    # database when rewriting fetch targets from a reconciled snapshot.
    now = utcnow()
    current_claims_by_id = {
        target.fetch_target_id: target
        for target in current_fetch_targets
        if target.fetch_claim_expires_at and target.fetch_claim_expires_at > now
    }
    for target in tracker_fetch_targets:
        current = current_claims_by_id.get(target.fetch_target_id)
        if current is None or current.fetch_claim_expires_at is None:
            continue
        target.fetch_claim_owner = current.fetch_claim_owner
        target.fetch_claim_expires_at = current.fetch_claim_expires_at


def sync_and_persist(repository: Repository, *, today: date | None = None) -> AppSnapshot:
    repository.ensure_data_dir()
    today = today or date.today()

    app_state = repository.load_app_state()
    trip_groups = repository.load_trip_groups()
    trips = repository.load_trips()
    rule_group_targets = repository.load_rule_group_targets()
    route_options = repository.load_route_options()
    existing_trip_instances = repository.load_trip_instances()
    existing_trip_instance_group_memberships = repository.load_trip_instance_group_memberships()
    existing_trackers = repository.load_trackers()
    existing_fetch_targets = repository.load_tracker_fetch_targets()
    bookings = repository.load_bookings()
    unmatched_bookings = repository.load_unmatched_bookings()
    booking_email_events = repository.load_booking_email_events()
    price_records = repository.load_price_records()

    trip_instances = reconcile_trip_instances(
        trips,
        existing_trip_instances,
        today=today,
        future_weeks=app_state.future_weeks,
    )
    trip_instance_group_memberships = reconcile_trip_instance_group_memberships(
        trips=trips,
        rule_group_targets=rule_group_targets,
        trip_instances=trip_instances,
        existing_memberships=existing_trip_instance_group_memberships,
    )
    trackers = reconcile_trackers(trips, trip_instances, route_options, existing_trackers)
    tracker_fetch_targets = reconcile_fetch_targets(
        trackers,
        trips,
        trip_instances,
        existing_fetch_targets,
    )

    valid_trip_instance_ids = {item.trip_instance_id for item in trip_instances}
    filtered_bookings: list[Booking] = []
    for booking in bookings:
        if booking.trip_instance_id not in valid_trip_instance_ids:
            continue
        filtered_bookings.append(booking)
    bookings = reconcile_booking_route_options(
        bookings=filtered_bookings,
        trackers=trackers,
    )
    bookings, unmatched_bookings = reconcile_unmatched_bookings(
        bookings=bookings,
        unmatched_bookings=unmatched_bookings,
        trip_instances=trip_instances,
        trackers=trackers,
    )
    for unmatched in unmatched_bookings:
        unmatched.candidate_trip_instance_ids = _filter_candidate_trip_ids(
            unmatched.candidate_trip_instance_ids,
            valid_trip_instance_ids,
        )

    apply_fetch_target_rollups(trackers, tracker_fetch_targets)
    recompute_trip_states(trip_instances, trackers, bookings, today=today)

    with repository.transaction():
        current_fetch_targets = repository.load_tracker_fetch_targets()
        _preserve_active_fetch_claims(
            tracker_fetch_targets,
            current_fetch_targets,
        )
        repository.save_trip_instances(trip_instances)
        repository.save_trip_instance_group_memberships(trip_instance_group_memberships)
        repository.save_trackers(trackers)
        repository.save_tracker_fetch_targets(tracker_fetch_targets)
        repository.save_unmatched_bookings(unmatched_bookings)
        repository.save_bookings(bookings)

    return AppSnapshot(
        trip_groups=trip_groups,
        trips=trips,
        rule_group_targets=rule_group_targets,
        route_options=route_options,
        trip_instances=trip_instances,
        trip_instance_group_memberships=trip_instance_group_memberships,
        trackers=trackers,
        tracker_fetch_targets=tracker_fetch_targets,
        bookings=bookings,
        unmatched_bookings=unmatched_bookings,
        booking_email_events=booking_email_events,
        price_records=price_records,
        app_state=app_state,
    )
