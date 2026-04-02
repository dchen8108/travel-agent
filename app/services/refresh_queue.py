from __future__ import annotations

from datetime import date

from app.services.background_fetch import queue_rolling_refresh
from app.services.dashboard import AppSnapshot, horizon_instances_for_trip
from app.storage.repository import Repository


def queued_refresh_message(base_message: str, queued_count: int) -> str:
    if queued_count == 1:
        return f"{base_message}. Refresh queued for 1 airport-pair search."
    if queued_count > 1:
        return f"{base_message}. Refresh queued for {queued_count} airport-pair searches."
    return base_message


def queue_refresh_for_trip(
    snapshot: AppSnapshot,
    repository: Repository,
    *,
    trip_id: str,
    today: date | None = None,
    include_test_data: bool = True,
) -> int:
    today = today or date.today()
    trip_instance_ids = {
        instance.trip_instance_id
        for instance in horizon_instances_for_trip(snapshot, trip_id, today=today)
        if instance.travel_state != "skipped"
    }
    return queue_refresh_for_trip_instances(
        snapshot,
        repository,
        trip_instance_ids=trip_instance_ids,
        include_test_data=include_test_data,
    )


def queue_refresh_for_trip_instance(
    snapshot: AppSnapshot,
    repository: Repository,
    *,
    trip_instance_id: str,
    include_test_data: bool = True,
) -> int:
    return queue_refresh_for_trip_instances(
        snapshot,
        repository,
        trip_instance_ids={trip_instance_id},
        include_test_data=include_test_data,
    )


def queue_refresh_for_trip_instances(
    snapshot: AppSnapshot,
    repository: Repository,
    *,
    trip_instance_ids: set[str],
    include_test_data: bool = True,
) -> int:
    if not trip_instance_ids:
        return 0
    queued_count = queue_rolling_refresh(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        trip_instance_ids=trip_instance_ids,
        include_test_data=include_test_data,
    )
    if queued_count:
        repository.save_tracker_fetch_targets(snapshot.tracker_fetch_targets)
    return queued_count
