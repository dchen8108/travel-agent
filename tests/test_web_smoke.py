from __future__ import annotations

from datetime import date, timedelta
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

    for path in ["/", "/trips", "/trips/new", "/trips/new-past", "/bookings", "/bookings/new", "/imports", "/resolve", "/trackers"]:
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

    pause_from_page = client.post(
        f"/trips/{trip_id}/pause",
        headers={"referer": "http://testserver/trips?q=Test+Weekly+Trip"},
        follow_redirects=False,
    )
    assert pause_from_page.status_code == 303
    assert pause_from_page.headers["location"] == "/trips?q=Test+Weekly+Trip&message=Trip+paused"

    activate_from_page = client.post(
        f"/trips/{trip_id}/activate",
        headers={"referer": "http://testserver/trips?q=Test+Weekly+Trip"},
        follow_redirects=False,
    )
    assert activate_from_page.status_code == 303
    assert activate_from_page.headers["location"] == "/trips?q=Test+Weekly+Trip&message=Trip+activated"


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
    assert "Show in scheduled" not in trips_page.text


def test_skipped_trip_moves_out_of_main_scheduled_list_and_can_be_restored(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    create = client.post(
        "/trips",
        data={
            "label": "Doctor Visit Flight",
            "trip_kind": "one_time",
            "anchor_date": "2026-05-10",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["LAX"],"destination_airports":["SEA"],"airlines":["Delta"],"day_offset":0,"start_time":"07:00","end_time":"11:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    trip_location = create.headers["location"]
    trip_id = trip_location.split("/trips/")[1].split("?")[0]
    trips_page = client.get(f"/trips?q=Doctor+Visit+Flight")
    assert trips_page.status_code == 200
    marker = 'id="scheduled-'
    assert marker in trips_page.text
    trip_instance_id = trips_page.text.split(marker, 1)[1].split('"', 1)[0]

    skip = client.post(
        f"/trip-instances/{trip_instance_id}/skip",
        headers={"referer": "http://testserver/trips?q=Doctor+Visit+Flight"},
        follow_redirects=False,
    )
    assert skip.status_code == 303
    assert skip.headers["location"] == "/trips?q=Doctor+Visit+Flight&message=Trip+skipped"

    trips_page = client.get("/trips")
    assert trips_page.status_code == 200
    assert "Unskip" not in trips_page.text
    assert "No scheduled trips match these filters." in trips_page.text

    skipped_page = client.get("/trips?show_skipped=true")
    assert skipped_page.status_code == 200
    assert "Doctor Visit Flight" in skipped_page.text
    assert "Unskip" in skipped_page.text

    restore = client.post(
        f"/trip-instances/{trip_instance_id}/restore",
        headers={"referer": "http://testserver/trips?show_skipped=true"},
        follow_redirects=False,
    )
    assert restore.status_code == 303
    assert restore.headers["location"] == "/trips?show_skipped=true&message=Trip+restored"

    restored_page = client.get("/trips")
    assert restored_page.status_code == 200
    assert "Doctor Visit Flight" in restored_page.text


def test_recurring_trip_preview_shows_full_horizon_and_marks_skipped_dates(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    create = client.post(
        "/trips",
        data={
            "label": "Weekly Commute",
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    trip_location = create.headers["location"]
    trip_id = trip_location.split("/trips/")[1].split("?")[0]
    trips_page = client.get(f"/trips?recurring_trip_id={trip_id}")
    assert trips_page.status_code == 200
    marker = 'id="scheduled-'
    assert marker in trips_page.text
    trip_instance_id = trips_page.text.split(marker, 1)[1].split('"', 1)[0]

    skip = client.post(
        f"/trip-instances/{trip_instance_id}/skip",
        headers={"referer": f"http://testserver/trips?recurring_trip_id={trip_id}"},
        follow_redirects=False,
    )
    assert skip.status_code == 303
    assert skip.headers["location"] == f"/trips?recurring_trip_id={trip_id}&message=Trip+skipped"

    trips_page = client.get("/trips")
    assert trips_page.status_code == 200
    assert trips_page.text.count('class="badge horizon-badge') == 12
    assert 'class="badge horizon-badge is-skipped"' in trips_page.text


def test_trip_detail_redirects_to_filtered_trips_view(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    create = client.post(
        "/trips",
        data={
            "label": "Redirect Weekly Trip",
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    trip_id = create.headers["location"].split("/trips/")[1].split("?")[0]

    response = client.get(f"/trips/{trip_id}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/trips?recurring_trip_id={trip_id}#recurring-{trip_id}"


def test_scheduled_trips_can_be_filtered_to_specific_recurring_parents(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    weekly_one = client.post(
        "/trips",
        data={
            "label": "Weekly Commute A",
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    weekly_two = client.post(
        "/trips",
        data={
            "label": "Weekly Commute B",
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Tuesday",
            "route_options_json": '[{"origin_airports":["LAX"],"destination_airports":["SEA"],"airlines":["Delta"],"day_offset":0,"start_time":"07:00","end_time":"11:00"}]',
        },
        follow_redirects=False,
    )
    standalone = client.post(
        "/trips",
        data={
            "label": "One-off Flight",
            "trip_kind": "one_time",
            "anchor_date": "2026-05-10",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["SFO"],"destination_airports":["JFK"],"airlines":["United"],"day_offset":0,"start_time":"08:00","end_time":"12:00"}]',
        },
        follow_redirects=False,
    )
    assert weekly_one.status_code == 303
    assert weekly_two.status_code == 303
    assert standalone.status_code == 303

    weekly_one_id = weekly_one.headers["location"].split("/trips/")[1].split("?")[0]

    filtered_page = client.get(f"/trips?recurring_trip_id={weekly_one_id}")
    assert filtered_page.status_code == 200
    assert "Weekly Commute A" in filtered_page.text
    assert "One-off Flight" not in filtered_page.text


def test_scheduled_partial_renders_live_filter_surface(tmp_path: Path) -> None:
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
            "label": "Weekly Commute Filter Test",
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )

    partial = client.get("/trips?partial=scheduled&show_skipped=true")
    assert partial.status_code == 200
    assert 'data-scheduled-filter-form' in partial.text
    assert "Show skipped" in partial.text
    assert "Apply filters" in partial.text


def test_trips_page_moves_past_trips_into_history_section(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    today = date.today()

    client.post(
        "/trips",
        data={
            "label": "Past Commute",
            "trip_kind": "one_time",
            "anchor_date": (today - timedelta(days=1)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    client.post(
        "/trips",
        data={
            "label": "Future Commute",
            "trip_kind": "one_time",
            "anchor_date": (today + timedelta(days=2)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )

    trips_page = client.get("/trips")
    assert trips_page.status_code == 200
    assert "Past trips" in trips_page.text
    assert "Showing 1 scheduled trip and 1 past trip." in trips_page.text
    assert 'id="scheduled-' in trips_page.text
    assert 'id="past-' in trips_page.text


def test_log_past_trip_flow_can_redirect_to_history_or_booking(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    past_date = (date.today() - timedelta(days=7)).isoformat()

    save_only = client.post(
        "/trips/past",
        data={
            "label": "Old commute",
            "anchor_date": past_date,
            "redirect_mode": "trips",
        },
        follow_redirects=False,
    )
    assert save_only.status_code == 303
    assert "/trips?" in save_only.headers["location"]
    assert "message=Past+trip+logged" in save_only.headers["location"]

    trips_page = client.get("/trips")
    assert "Old commute" in trips_page.text
    assert "Add booking" in trips_page.text

    save_and_add = client.post(
        "/trips/past",
        data={
            "label": "Booked history",
            "anchor_date": past_date,
            "redirect_mode": "booking",
        },
        follow_redirects=False,
    )
    assert save_and_add.status_code == 303
    assert save_and_add.headers["location"].startswith("/bookings/new?trip_instance_id=")
    assert "message=Past+trip+logged" in save_and_add.headers["location"]


def test_skipped_trips_do_not_appear_in_past_history_even_when_show_skipped_is_enabled(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    today = date.today()

    create = client.post(
        "/trips",
        data={
            "label": "Skip me later",
            "trip_kind": "one_time",
            "anchor_date": (today - timedelta(days=1)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    trips_page = client.get("/trips?q=Skip+me+later")
    trip_instance_id = trips_page.text.split('id="past-', 1)[1].split('"', 1)[0]

    skip = client.post(
        f"/trip-instances/{trip_instance_id}/skip",
        headers={"referer": "http://testserver/trips?q=Skip+me+later&show_skipped=true"},
        follow_redirects=False,
    )
    assert skip.status_code == 303

    trips_page = client.get("/trips?show_skipped=true&q=Skip+me+later")
    assert 'id="past-' not in trips_page.text
    assert "No past trips yet." in trips_page.text
