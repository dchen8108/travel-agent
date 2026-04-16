from __future__ import annotations

from datetime import date

from app.routes import groups as groups_route
from app.routes import trackers as trackers_route
from app.routes import trips as trips_route
from app.routes import today as today_route
from app.services.bookings import BookingCandidate, record_booking
from app.services.dashboard_navigation import trip_focus_url
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

    response = client.get(f"/trip-instances/{instance.trip_instance_id}", follow_redirects=False)

    assert response.status_code == 303
    assert "panel=trackers" in response.headers["location"]
    assert calls["persisted"] == 1


def test_dashboard_uses_persisted_snapshot(client, repository: Repository, monkeypatch) -> None:
    _seed_one_time_trip(repository)
    real = today_route.load_persisted_snapshot
    calls = {"persisted": 0}

    def wrapped(repo):
        calls["persisted"] += 1
        return real(repo)

    monkeypatch.setattr(today_route, "load_persisted_snapshot", wrapped)

    response = client.get("/")

    assert response.status_code == 200
    assert calls["persisted"] == 1


def test_trackers_detail_redirects_to_bookings_panel_when_bookings_exist(
    client,
    repository: Repository,
) -> None:
    _trip, instance = _seed_one_time_trip(repository)
    record_booking(
        repository,
        BookingCandidate(
            airline="American",
            origin_airport="LAX",
            destination_airport="JFK",
            departure_date=instance.anchor_date,
            departure_time="09:00",
            arrival_time="17:00",
            booked_price=50000,
            record_locator="ABC123",
        ),
        trip_instance_id=instance.trip_instance_id,
    )

    response = client.get(f"/trip-instances/{instance.trip_instance_id}", follow_redirects=False)

    assert response.status_code == 303
    assert "panel=bookings" in response.headers["location"]


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

    response = client.get(f"/groups/{group.trip_group_id}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/#group-{group.trip_group_id}"
    assert calls["persisted"] == 1


def test_group_edit_uses_persisted_snapshot(client, repository: Repository, monkeypatch) -> None:
    group = save_trip_group(repository, trip_group_id=None, label="Editable Group")
    real = groups_route.load_persisted_snapshot
    calls = {"persisted": 0}

    def wrapped(repo):
        calls["persisted"] += 1
        return real(repo)

    monkeypatch.setattr(groups_route, "load_persisted_snapshot", wrapped)

    response = client.get(f"/groups/{group.trip_group_id}/edit")

    assert response.status_code == 200
    assert f'value="{group.label}"' in response.text
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

    monkeypatch.setattr(trips_route, "load_persisted_snapshot", wrapped)

    response = client.get(f"/trips/{trip.trip_id}", follow_redirects=False)

    assert response.status_code == 303
    snapshot = real(repository)
    assert response.headers["location"] == trip_focus_url(
        snapshot,
        trip.trip_id,
        trip_instance_id=instance.trip_instance_id,
    )
    assert calls["persisted"] == 1
