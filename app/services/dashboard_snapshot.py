from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date
from pathlib import Path
from threading import Lock

from app.services.data_scope import filter_snapshot, include_test_data_for_ui
from app.services.snapshots import AppSnapshot
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


_snapshot_cache_lock = Lock()
type SnapshotFileSignature = tuple[Path, int, int]
type SnapshotSignature = tuple[SnapshotFileSignature, ...]


_snapshot_cache_entry: tuple[SnapshotSignature, AppSnapshot] | None = None


def _path_signature(path: Path) -> SnapshotFileSignature:
    resolved = path.resolve()
    if not path.exists():
        return resolved, 0, 0
    stat_result = path.stat()
    return resolved, stat_result.st_mtime_ns, stat_result.st_size


def _snapshot_signature(repository: Repository) -> SnapshotSignature:
    repository.ensure_data_dir()
    db_path = repository.db_path
    wal_path = Path(f"{db_path}-wal")
    shm_path = Path(f"{db_path}-shm")
    return (
        _path_signature(db_path),
        _path_signature(wal_path),
        _path_signature(shm_path),
        _path_signature(repository.app_state_path),
    )


def _load_snapshot_uncached(repository: Repository) -> AppSnapshot:
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
        price_records=[],
        app_state=app_state,
    )
    return filter_snapshot(snapshot, include_test_data=include_test_data_for_ui(app_state))


def _ui_snapshot(snapshot: AppSnapshot) -> AppSnapshot:
    if snapshot.price_records:
        return replace(snapshot, price_records=[])
    return snapshot


def _store_snapshot_cache(repository: Repository, snapshot: AppSnapshot) -> AppSnapshot:
    global _snapshot_cache_entry
    ui_snapshot = _ui_snapshot(snapshot)
    with _snapshot_cache_lock:
        _snapshot_cache_entry = (_snapshot_signature(repository), deepcopy(ui_snapshot))
    return ui_snapshot


def load_persisted_snapshot(repository: Repository) -> AppSnapshot:
    """Load the last persisted runtime snapshot without mutating state."""
    signature = _snapshot_signature(repository)
    with _snapshot_cache_lock:
        if _snapshot_cache_entry is not None and _snapshot_cache_entry[0] == signature:
            return deepcopy(_snapshot_cache_entry[1])
    return _store_snapshot_cache(repository, _load_snapshot_uncached(repository))


def load_live_snapshot(repository: Repository, *, today: date | None = None) -> AppSnapshot:
    """Run the heavyweight reconcile-and-persist workflow, then return the filtered snapshot.

    This exists for mutation flows and jobs that need to repair derived runtime state.
    Normal page reads should prefer load_persisted_snapshot().
    """
    repository.ensure_data_dir()
    snapshot = sync_and_persist(repository, today=today)
    filtered_snapshot = filter_snapshot(snapshot, include_test_data=include_test_data_for_ui(snapshot.app_state))
    return _store_snapshot_cache(repository, filtered_snapshot)
