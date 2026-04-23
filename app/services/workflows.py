from __future__ import annotations

from datetime import date
from typing import Callable, Hashable, TypeVar

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

ModelT = TypeVar("ModelT")


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


def _diff_models(
    current_items: list[ModelT],
    desired_items: list[ModelT],
    *,
    key: Callable[[ModelT], Hashable],
) -> tuple[list[ModelT], list[Hashable]]:
    current_by_key = {
        key(item): item.model_dump(mode="json")
        for item in current_items
    }
    desired_by_key = {
        key(item): item.model_dump(mode="json")
        for item in desired_items
    }
    changed_items = [
        item
        for item in desired_items
        if current_by_key.get(key(item)) != desired_by_key[key(item)]
    ]
    removed_keys = [
        item_key
        for item_key in current_by_key
        if item_key not in desired_by_key
    ]
    return changed_items, removed_keys


def build_reconciled_snapshot(
    repository: Repository,
    *,
    today: date | None = None,
    include_price_records: bool = False,
) -> AppSnapshot:
    """Recompute runtime-derived state from authored trips, routes, bookings, and fetch data."""
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
    price_records = repository.load_price_records() if include_price_records else []

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
        app_state=app_state,
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

    apply_fetch_target_rollups(trackers, tracker_fetch_targets, app_state=app_state)
    recompute_trip_states(trip_instances, trackers, bookings, today=today)

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


def persist_reconciled_snapshot(repository: Repository, snapshot: AppSnapshot) -> AppSnapshot:
    """Diff a reconciled snapshot against persisted runtime tables and write only changed rows."""
    with repository.transaction():
        current_trip_instances = repository.load_trip_instances()
        current_memberships = repository.load_trip_instance_group_memberships()
        current_trackers = repository.load_trackers()
        current_fetch_targets = repository.load_tracker_fetch_targets()
        current_bookings = repository.load_bookings()
        current_unmatched_bookings = repository.load_unmatched_bookings()
        _preserve_active_fetch_claims(
            snapshot.tracker_fetch_targets,
            current_fetch_targets,
        )

        trip_instances_to_upsert, trip_instance_ids_to_delete = _diff_models(
            current_trip_instances,
            snapshot.trip_instances,
            key=lambda item: item.trip_instance_id,
        )
        memberships_to_upsert, membership_keys_to_delete = _diff_models(
            current_memberships,
            snapshot.trip_instance_group_memberships,
            key=lambda item: (item.trip_instance_id, item.trip_group_id),
        )
        trackers_to_upsert, tracker_ids_to_delete = _diff_models(
            current_trackers,
            snapshot.trackers,
            key=lambda item: item.tracker_id,
        )
        fetch_targets_to_upsert, fetch_target_ids_to_delete = _diff_models(
            current_fetch_targets,
            snapshot.tracker_fetch_targets,
            key=lambda item: item.fetch_target_id,
        )
        bookings_to_upsert, booking_ids_to_delete = _diff_models(
            current_bookings,
            snapshot.bookings,
            key=lambda item: item.booking_id,
        )
        unmatched_to_upsert, unmatched_ids_to_delete = _diff_models(
            current_unmatched_bookings,
            snapshot.unmatched_bookings,
            key=lambda item: item.booking_id,
        )

        repository.upsert_trip_instances(trip_instances_to_upsert)
        repository.upsert_trackers(trackers_to_upsert)
        repository.upsert_tracker_fetch_targets(fetch_targets_to_upsert)
        repository.upsert_bookings(bookings_to_upsert)
        repository.upsert_unmatched_bookings(unmatched_to_upsert)
        repository.upsert_trip_instance_group_memberships(memberships_to_upsert)

        repository.delete_bookings_by_ids([str(item) for item in booking_ids_to_delete])
        repository.delete_unmatched_bookings_by_ids([str(item) for item in unmatched_ids_to_delete])
        repository.delete_tracker_fetch_targets_by_ids([str(item) for item in fetch_target_ids_to_delete])
        repository.delete_trackers_by_ids([str(item) for item in tracker_ids_to_delete])
        repository.delete_trip_instance_group_memberships_by_keys(
            [(str(trip_instance_id), str(trip_group_id)) for trip_instance_id, trip_group_id in membership_keys_to_delete]
        )
        repository.delete_trip_instances_by_ids([str(item) for item in trip_instance_ids_to_delete])
    return snapshot


def sync_and_persist(
    repository: Repository,
    *,
    today: date | None = None,
    include_price_records: bool = False,
) -> AppSnapshot:
    """Reconcile the full runtime snapshot and persist any resulting runtime-table changes."""
    snapshot = build_reconciled_snapshot(
        repository,
        today=today,
        include_price_records=include_price_records,
    )
    return persist_reconciled_snapshot(repository, snapshot)
