from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.base import DataScope
from app.services.bookings import BookingCandidate, record_booking
from app.services.groups import save_trip_group
from app.services.trip_instances import set_trip_instance_skipped
from app.services.trips import save_trip
from app.services.workflows import sync_and_persist
from app.settings import Settings
from app.storage.repository import Repository


def _seed_v2_trip(repository: Repository, *, booked: bool = True) -> tuple[str, date]:
    today = date.today()
    travel_date = today + timedelta(days=5)
    group = save_trip_group(repository, trip_group_id=None, label="Work")
    trip = save_trip(
        repository,
        trip_id=None,
        label="Monday commute",
        trip_kind="one_time",
        active=True,
        anchor_date=travel_date,
        anchor_weekday=travel_date.strftime("%A"),
        trip_group_ids=[group.trip_group_id],
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "Southwest",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "08:00",
            }
        ],
        data_scope=DataScope.LIVE,
    )
    snapshot = sync_and_persist(repository, today=today)
    instance = next(item for item in snapshot.trip_instances if item.trip_id == trip.trip_id)
    if booked:
        record_booking(
            repository,
            BookingCandidate(
                airline="Southwest",
                origin_airport="LAX",
                destination_airport="SFO",
                departure_date=travel_date,
                departure_time="06:15",
                arrival_time="07:35",
                booked_price="88.40",
                record_locator="V2TEST",
            ),
            trip_instance_id=instance.trip_instance_id,
        )
        sync_and_persist(repository, today=today)
    return instance.trip_instance_id, travel_date


def test_v2_workspace_api_exposes_parallel_decision_contract(client, repository: Repository) -> None:
    trip_instance_id, _ = _seed_v2_trip(repository)

    response = client.get("/api/v2/workspace")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == 2
    assert payload["stats"]["departuresNext14Days"] == 1
    assert payload["stats"]["bookedNext14Days"] == 1
    assert payload["collections"][0]["label"] == "Work"
    assert payload["trips"][0]["state"] == "booked"
    assert payload["trips"][0]["daysUntil"] == 5
    assert payload["trips"][0]["row"]["trip"]["tripInstanceId"] == trip_instance_id
    assert payload["trips"][0]["row"]["trip"]["title"] == "Monday commute"


def test_v2_workspace_includes_skipped_trips_without_changing_v1_default(
    client,
    repository: Repository,
) -> None:
    trip_instance_id, _ = _seed_v2_trip(repository, booked=False)
    set_trip_instance_skipped(repository, trip_instance_id, skipped=True)

    v2_response = client.get("/api/v2/workspace")
    v1_response = client.get("/api/dashboard")

    assert v2_response.status_code == 200
    assert v2_response.json()["trips"][0]["state"] == "skipped"
    assert v1_response.status_code == 200
    assert v1_response.json()["trips"] == []


def test_v2_shell_bootstraps_only_the_v2_workspace(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text(
        '<html><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        frontend_dist_dir=dist_dir,
    )
    client = TestClient(create_app(settings))

    response = client.get("/v2/schedule")

    assert response.status_code == 200
    assert '"v2Workspace"' in response.text
    assert '"version":2' in response.text
    assert '"dashboard"' not in response.text
