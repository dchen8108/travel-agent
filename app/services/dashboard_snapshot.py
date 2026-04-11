from __future__ import annotations

from datetime import date

from app.services.data_scope import filter_snapshot, include_test_data_for_ui
from app.services.snapshots import AppSnapshot
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


def load_persisted_snapshot(repository: Repository) -> AppSnapshot:
    """Load the last persisted runtime snapshot without mutating state."""
    repository.ensure_data_dir()
    app_state = repository.load_app_state()
    snapshot = AppSnapshot(
        trip_groups=repository.load_trip_groups(),
        trips=repository.load_trips(),
        rule_group_targets=repository.load_rule_group_targets(),
        route_options=repository.load_route_options(),
        trip_instances=repository.load_trip_instances(),
        trip_instance_group_memberships=repository.load_trip_instance_group_memberships(),
        trackers=repository.load_trackers(),
        tracker_fetch_targets=repository.load_tracker_fetch_targets(),
        bookings=repository.load_bookings(),
        unmatched_bookings=repository.load_unmatched_bookings(),
        booking_email_events=repository.load_booking_email_events(),
        price_records=repository.load_price_records(),
        app_state=app_state,
    )
    return filter_snapshot(snapshot, include_test_data=include_test_data_for_ui(app_state))


def load_live_snapshot(repository: Repository, *, today: date | None = None) -> AppSnapshot:
    """Run the heavyweight reconcile-and-persist workflow, then return the filtered snapshot."""
    repository.ensure_data_dir()
    snapshot = sync_and_persist(repository, today=today)
    return filter_snapshot(snapshot, include_test_data=include_test_data_for_ui(snapshot.app_state))
