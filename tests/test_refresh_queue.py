from __future__ import annotations

from datetime import date, timedelta

from app.services.refresh_queue import queue_refresh_for_trip_instance
from app.services.trips import save_trip
from app.services.workflows import sync_and_persist


def test_queue_refresh_upserts_only_changed_fetch_targets(repository, monkeypatch) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Queued refresh trip",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=7),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX",
                "destination_airports": "SFO",
                "airlines": "Southwest",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )
    snapshot = sync_and_persist(repository)
    trip_instance = next(item for item in snapshot.trip_instances if item.trip_id == trip.trip_id)
    original_targets = {target.fetch_target_id for target in snapshot.tracker_fetch_targets}

    saved_called = False
    upserted_ids: list[str] = []

    def fail_save(_targets):
        nonlocal saved_called
        saved_called = True

    def record_upsert(targets):
        upserted_ids.extend(target.fetch_target_id for target in targets)

    monkeypatch.setattr(repository, "replace_tracker_fetch_targets", fail_save)
    monkeypatch.setattr(repository, "upsert_tracker_fetch_targets", record_upsert)

    queued_count = queue_refresh_for_trip_instance(
        snapshot,
        repository,
        trip_instance_id=trip_instance.trip_instance_id,
    )

    assert queued_count == len(upserted_ids)
    assert queued_count > 0
    assert not saved_called
    assert set(upserted_ids).issubset(original_targets)
