from __future__ import annotations

from datetime import date

from app.routes import groups as groups_route
from app.routes import trackers as trackers_route
from app.routes import trips as trips_route
from app.services.groups import save_trip_group
from app.services.trips import save_trip
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


def _seed_one_time_trip(repository: Repository):
    trip = save_trip(
        repository,
        trip_id=None,
        label="Snapshot Loading Trip",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 20),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "JFK",
                "airlines": "American",
                "day_offset": 0,
                "start_time": "08:00",
                "end_time": "12:00",
            }
        ],
    )
    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    instance = next(item for item in snapshot.trip_instances if item.trip_id == trip.trip_id and not item.deleted)
    return trip, instance


def test_trackers_detail_uses_persisted_snapshot(client, repository: Repository, monkeypatch) -> None:
    _trip, instance = _seed_one_time_trip(repository)
    real = trackers_route.load_persisted_snapshot
    calls = {"persisted": 0}

    def wrapped(repo):
        calls["persisted"] += 1
        return real(repo)

    monkeypatch.setattr(trackers_route, "load_persisted_snapshot", wrapped)

    response = client.get(f"/trip-instances/{instance.trip_instance_id}")

    assert response.status_code == 200
    assert calls["persisted"] == 1


def test_group_detail_uses_persisted_snapshot(client, repository: Repository, monkeypatch) -> None:
    group = save_trip_group(repository, trip_group_id=None, label="Snapshot Group")
    save_trip(
        repository,
        trip_id=None,
        label="Snapshot Rule",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
        trip_group_ids=[group.trip_group_id],
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )
    sync_and_persist(repository, today=date(2026, 4, 1))
    real = groups_route.load_persisted_snapshot
    calls = {"persisted": 0}

    def wrapped(repo):
        calls["persisted"] += 1
        return real(repo)

    monkeypatch.setattr(groups_route, "load_persisted_snapshot", wrapped)

    response = client.get(f"/groups/{group.trip_group_id}")

    assert response.status_code == 200
    assert calls["persisted"] == 1


def test_trip_detail_prefers_persisted_snapshot_when_instance_exists(
    client,
    repository: Repository,
    monkeypatch,
) -> None:
    trip, instance = _seed_one_time_trip(repository)
    real = trips_route.load_persisted_snapshot
    calls = {"persisted": 0}

    def wrapped(repo):
        calls["persisted"] += 1
        return real(repo)

    def boom(*_args, **_kwargs):
        raise AssertionError("trip_detail should not fall back to live snapshot when a persisted instance exists")

    monkeypatch.setattr(trips_route, "load_persisted_snapshot", wrapped)
    monkeypatch.setattr(trips_route, "load_live_snapshot", boom)

    response = client.get(f"/trips/{trip.trip_id}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/trip-instances/{instance.trip_instance_id}"
    assert calls["persisted"] == 1
