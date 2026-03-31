from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def test_core_pages_render(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    for path in ["/", "/trips", "/trips/new", "/bookings", "/bookings/new", "/imports", "/resolve", "/trackers"]:
        response = client.get(path)
        assert response.status_code == 200


def test_trip_creation_and_booking_flow(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/trips",
        data={
            "label": "LA to SF Outbound",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR","LAX"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    trips_page = client.get("/trips")
    assert "LA to SF Outbound" in trips_page.text

    booking_page = client.get("/bookings/new")
    assert booking_page.status_code == 200

    booking_response = client.post(
        "/bookings",
        data={
            "trip_instance_id": "",
            "tracker_id": "",
            "airline": "Alaska",
            "origin_airport": "BUR",
            "destination_airport": "SFO",
            "departure_date": "2026-04-06",
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "ABC123",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert booking_response.status_code == 303

    bookings_page = client.get("/bookings")
    assert "ABC123" in bookings_page.text


def test_pause_and_activate_trip_redirect_to_trips_by_default(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/trips",
        data={
            "label": "Test Weekly Trip",
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    trip_location = response.headers["location"]
    trip_id = trip_location.split("/trips/")[1].split("?")[0]

    pause = client.post(f"/trips/{trip_id}/pause", follow_redirects=False)
    assert pause.status_code == 303
    assert pause.headers["location"] == "/trips?message=Trip+paused"

    activate = client.post(f"/trips/{trip_id}/activate", follow_redirects=False)
    assert activate.status_code == 303
    assert activate.headers["location"] == "/trips?message=Trip+activated"


def test_trips_page_separates_recurring_plans_from_scheduled_trips(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    client.post(
        "/trips",
        data={
            "label": "Weekly LA to SF",
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    client.post(
        "/trips",
        data={
            "label": "Conference Arrival",
            "trip_kind": "one_time",
            "anchor_date": "2026-05-10",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["LAX"],"destination_airports":["SEA"],"airlines":["Delta"],"day_offset":0,"start_time":"07:00","end_time":"11:00"}]',
        },
        follow_redirects=False,
    )

    trips_page = client.get("/trips")
    assert trips_page.status_code == 200
    assert "Recurring trips" in trips_page.text
    assert "Scheduled trips" in trips_page.text
    assert "Weekly LA to SF" in trips_page.text
    assert "Conference Arrival" in trips_page.text
