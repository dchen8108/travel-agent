from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.base import FetchTargetStatus, utcnow
from app.settings import Settings
from app.storage.repository import Repository


def test_core_pages_render(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    for path in ["/", "/trips", "/trips/new", "/bookings", "/bookings/new", "/resolve", "/trackers"]:
        response = client.get(path)
        assert response.status_code == 200
    trackers_redirect = client.get("/trackers", follow_redirects=False)
    assert trackers_redirect.status_code == 303
    assert trackers_redirect.headers["location"] == "/trips"


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


def test_trip_creation_queues_refresh_targets_immediately(tmp_path: Path) -> None:
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
            "label": "Queued Refresh Trip",
            "trip_kind": "one_time",
            "anchor_date": (date.today() + timedelta(days=7)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR","LAX"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Refresh+queued+for+2+airport-pair+searches." in response.headers["location"]

    repository = Repository(settings)
    fetch_targets = repository.load_tracker_fetch_targets()
    assert len(fetch_targets) == 2
    assert all(target.next_fetch_not_before is not None for target in fetch_targets)
    assert all(target.last_fetch_status == FetchTargetStatus.PENDING for target in fetch_targets)


def test_trip_creation_persists_preference_mode_and_thresholds(tmp_path: Path) -> None:
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
            "label": "Preference Weighted Trip",
            "trip_kind": "one_time",
            "preference_mode": "ranked_bias",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": (
                '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],'
                '"day_offset":0,"start_time":"06:00","end_time":"10:00","savings_needed_vs_previous":0},'
                '{"origin_airports":["LAX"],"destination_airports":["SFO"],"airlines":["United"],'
                '"day_offset":0,"start_time":"18:00","end_time":"22:00","savings_needed_vs_previous":50}]'
            ),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    repository = Repository(settings)
    trip = repository.load_trips()[0]
    route_options = sorted(repository.load_route_options(), key=lambda item: item.rank)

    assert trip.preference_mode == "ranked_bias"
    assert route_options[0].savings_needed_vs_previous == 0
    assert route_options[1].savings_needed_vs_previous == 50

    detail = client.get(response.headers["location"])
    assert detail.status_code == 200
    assert "Respect option order" not in detail.text
    assert "cheaper by at least your configured amount" in detail.text


def test_booking_save_redirects_to_trip_instance_detail(tmp_path: Path) -> None:
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
            "label": "Booking Redirect Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

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
            "record_locator": "BOOK01",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert booking_response.status_code == 303
    assert booking_response.headers["location"].startswith("/trip-instances/")

    detail = client.get(booking_response.headers["location"])
    assert detail.status_code == 200
    assert "Scheduled trip" in detail.text
    assert "View plan" in detail.text


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
    assert (
        activate.headers["location"]
        == "/trips?message=Trip+activated.+Refresh+queued+for+12+airport-pair+searches."
    )

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
    assert (
        activate_from_page.headers["location"]
        == "/trips?q=Test+Weekly+Trip&message=Trip+activated.+Refresh+queued+for+12+airport-pair+searches."
    )


def test_trip_activation_queues_refresh_targets_immediately(tmp_path: Path) -> None:
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
            "label": "Activation Queue Trip",
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    trip_id = response.headers["location"].split("/trips/")[1].split("?")[0]

    repository = Repository(settings)
    fetch_targets = repository.load_tracker_fetch_targets()
    delayed_until = utcnow() + timedelta(hours=6)
    for target in fetch_targets:
        target.next_fetch_not_before = delayed_until
    repository.save_tracker_fetch_targets(fetch_targets)

    pause = client.post(f"/trips/{trip_id}/pause", follow_redirects=False)
    assert pause.status_code == 303

    activate = client.post(f"/trips/{trip_id}/activate", follow_redirects=False)
    assert activate.status_code == 303
    assert "Trip+activated.+Refresh+queued+for+12+airport-pair+searches." in activate.headers["location"]

    refreshed_targets = repository.load_tracker_fetch_targets()
    assert len(refreshed_targets) == 12
    assert all(target.next_fetch_not_before is not None for target in refreshed_targets)
    assert all(target.next_fetch_not_before < delayed_until for target in refreshed_targets)


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
    assert "Log past trip" not in trips_page.text
    assert "Past trips" not in trips_page.text


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

    repository = Repository(settings)
    fetch_targets = repository.load_tracker_fetch_targets()
    delayed_until = utcnow() + timedelta(hours=6)
    for target in fetch_targets:
        target.next_fetch_not_before = delayed_until
    repository.save_tracker_fetch_targets(fetch_targets)

    restore = client.post(
        f"/trip-instances/{trip_instance_id}/restore",
        headers={"referer": "http://testserver/trips?show_skipped=true"},
        follow_redirects=False,
    )
    assert restore.status_code == 303
    assert (
        restore.headers["location"]
        == "/trips?show_skipped=true&message=Trip+restored.+Refresh+queued+for+1+airport-pair+search."
    )

    restored_page = client.get("/trips")
    assert restored_page.status_code == 200
    assert "Doctor Visit Flight" in restored_page.text
    refreshed_targets = repository.load_tracker_fetch_targets()
    assert len(refreshed_targets) == 1
    assert refreshed_targets[0].next_fetch_not_before is not None
    assert refreshed_targets[0].next_fetch_not_before < delayed_until


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


def test_trip_detail_renders_real_trip_page(tmp_path: Path) -> None:
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
    assert response.status_code == 200
    assert "Redirect Weekly Trip" in response.text
    assert "Route options" in response.text
    assert "Scheduled trips" in response.text


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


def test_past_trips_are_hidden_from_the_trips_ui(tmp_path: Path) -> None:
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
    assert "Past trips" not in trips_page.text
    assert "Log past trip" not in trips_page.text
    assert "Showing 1 scheduled trip." in trips_page.text
    assert 'id="scheduled-' in trips_page.text


def test_trip_trackers_page_shows_refresh_metadata(tmp_path: Path) -> None:
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
            "label": "Tracker metadata",
            "trip_kind": "one_time",
            "anchor_date": (date.today() + timedelta(days=7)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR","LAX"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    trips_page = client.get("/trips?q=Tracker+metadata")
    trip_instance_id = trips_page.text.split('href="/trip-instances/', 1)[1].split('"', 1)[0]
    trackers_page = client.get(f"/trip-instances/{trip_instance_id}/trackers")

    assert "Scheduled trip" in trackers_page.text
    assert "Tracker board" in trackers_page.text
    assert "Last updated:" in trackers_page.text
    assert "Next refresh:" in trackers_page.text
    assert "BUR to SFO" in trackers_page.text
    assert "LAX to SFO" in trackers_page.text


def test_trip_trackers_page_can_queue_a_rolling_refresh(tmp_path: Path) -> None:
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
            "label": "Refresh queue test",
            "trip_kind": "one_time",
            "anchor_date": (date.today() + timedelta(days=7)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR","LAX"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    trips_page = client.get("/trips?q=Refresh+queue+test")
    trip_instance_id = trips_page.text.split('href="/trip-instances/', 1)[1].split('"', 1)[0]
    queue = client.post(f"/trip-instances/{trip_instance_id}/trackers/queue-refresh", follow_redirects=False)
    assert queue.status_code == 303
    assert "Refresh+queued+for+2+airport-pair+searches." in queue.headers["location"]


def test_trip_trackers_page_shows_no_results_state_without_failure_copy(tmp_path: Path) -> None:
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
            "label": "No results tracker",
            "trip_kind": "one_time",
            "anchor_date": (date.today() + timedelta(days=7)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    repository = Repository(settings)
    fetch_targets = repository.load_tracker_fetch_targets()
    fetch_targets[0].last_fetch_status = FetchTargetStatus.NO_RESULTS
    fetch_targets[0].last_fetch_finished_at = utcnow()
    fetch_targets[0].next_fetch_not_before = utcnow() + timedelta(hours=4)
    fetch_targets[0].latest_price = None
    repository.save_tracker_fetch_targets(fetch_targets)

    trips_page = client.get("/trips?q=No+results+tracker")
    trip_instance_id = trips_page.text.split('href="/trip-instances/', 1)[1].split('"', 1)[0]
    trackers_page = client.get(f"/trip-instances/{trip_instance_id}/trackers")

    assert "No matching flights returned right now." in trackers_page.text
    assert "A recent Google Flights request failed. Travel Agent will retry automatically." not in trackers_page.text
    assert "is-unavailable" in trackers_page.text


def test_resolve_flow_redirects_to_trip_instance_detail(tmp_path: Path) -> None:
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
            "label": "Resolve Redirect Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    booking_response = client.post(
        "/bookings",
        data={
            "trip_instance_id": "",
            "tracker_id": "",
            "airline": "United",
            "origin_airport": "LAX",
            "destination_airport": "SEA",
            "departure_date": "2026-04-20",
            "departure_time": "09:10",
            "arrival_time": "11:35",
            "booked_price": "199",
            "record_locator": "UNMATCH1",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert booking_response.status_code == 303
    assert booking_response.headers["location"] == "/resolve?message=Booking+needs+resolution"

    resolve_page = client.get("/resolve")
    unmatched_id = resolve_page.text.split('/resolve/', 1)[1].split('/link', 1)[0]

    trips_page = client.get("/trips?q=Resolve+Redirect+Trip")
    trip_instance_id = trips_page.text.split('href="/trip-instances/', 1)[1].split('"', 1)[0]
    resolve_response = client.post(
        f"/resolve/{unmatched_id}/link",
        data={"trip_instance_id": trip_instance_id},
        follow_redirects=False,
    )
    assert resolve_response.status_code == 303
    assert resolve_response.headers["location"].startswith("/trip-instances/")


def test_past_trips_remain_hidden_even_when_show_skipped_is_enabled(tmp_path: Path) -> None:
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

    trips_page = client.get("/trips?show_skipped=true&q=Skip+me+later")
    assert 'id="past-' not in trips_page.text
    assert "Showing 0 scheduled trips." in trips_page.text
    assert "No scheduled trips match these filters." in trips_page.text
