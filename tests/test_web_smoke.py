from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.base import AppState
from app.models.base import FetchTargetStatus, utcnow
from app.services.bookings import BookingCandidate, record_booking
from app.services.groups import save_trip_group
from app.services.trips import save_trip
from app.settings import Settings
from app.storage.repository import Repository


def test_core_pages_render(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    for path in ["/", "/trips", "/trips/new", "/groups/new", "/bookings", "/resolve", "/trackers"]:
        response = client.get(path)
        assert response.status_code == 200
    trips_redirect = client.get("/trips", follow_redirects=False)
    assert trips_redirect.status_code == 303
    assert trips_redirect.headers["location"] == "/#all-travel"
    bookings_redirect = client.get("/bookings", follow_redirects=False)
    assert bookings_redirect.status_code == 303
    assert bookings_redirect.headers["location"] == "/#needs-linking"
    new_booking_redirect = client.get("/bookings/new", follow_redirects=False)
    assert new_booking_redirect.status_code == 303
    assert "Start+from+a+trip+to+add+a+booking." in new_booking_redirect.headers["location"]
    trackers_redirect = client.get("/trackers", follow_redirects=False)
    assert trackers_redirect.status_code == 303
    assert trackers_redirect.headers["location"] == "/#all-travel"


def test_trip_form_requires_at_least_one_route_option(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/trips",
        data={
            "label": "No Routes Yet",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "preference_mode": "equal",
            "route_options_json": "[]",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Trips require at least one route option." in response.text


def test_trip_form_rejects_overlapping_route_options(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/trips",
        data={
            "label": "Overlapping Routes",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "preference_mode": "equal",
            "route_options_json": (
                '[{"origin_airports":["BUR","LAX"],"destination_airports":["SFO"],"airlines":["Alaska","United"],'
                '"day_offset":0,"start_time":"06:00","end_time":"09:00"},'
                '{"origin_airports":["BUR"],"destination_airports":["SFO","OAK"],"airlines":["Alaska"],'
                '"day_offset":0,"start_time":"08:30","end_time":"10:00"}]'
            ),
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Route options 1 and 2 overlap." in response.text


def test_create_trip_from_booking_opens_prefilled_form_and_links_on_save(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)

    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Delta",
            origin_airport="LAX",
            destination_airport="SEA",
            departure_date=date(2026, 5, 10),
            departure_time="00:30",
            arrival_time="02:55",
            booked_price=189,
            record_locator="ZZZ999",
        ),
    )
    assert booking is None
    assert unmatched is not None

    form_page = client.get(
        f"/trips/new?unmatched_booking_id={unmatched.unmatched_booking_id}&trip_label=Conference%20Arrival"
    )
    assert form_page.status_code == 200
    assert "Starting from Booking ZZZ999." in form_page.text
    assert 'name="source_unmatched_booking_id" value="' + unmatched.unmatched_booking_id + '"' in form_page.text
    assert 'name="label" value="Conference Arrival"' in form_page.text
    assert '"origin_airports": ["LAX"]' in form_page.text
    assert '"destination_airports": ["SEA"]' in form_page.text

    save = client.post(
        "/trips",
        data={
            "label": "Conference Arrival",
            "trip_kind": "one_time",
            "source_unmatched_booking_id": unmatched.unmatched_booking_id,
            "anchor_date": "2026-05-10",
            "anchor_weekday": "",
            "preference_mode": "equal",
            "route_options_json": '[{"origin_airports":["LAX"],"destination_airports":["SEA"],"airlines":["Delta"],"day_offset":0,"start_time":"00:00","end_time":"02:30"}]',
        },
        follow_redirects=False,
    )
    assert save.status_code == 303
    assert save.headers["location"].startswith("/trip-instances/")

    stored_booking = next(item for item in repository.load_bookings() if item.record_locator == "ZZZ999")
    assert stored_booking.route_option_id != ""
    assert repository.load_unmatched_bookings() == []


def test_unmatched_booking_ui_does_not_fall_back_to_internal_ids(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)

    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Southwest",
            origin_airport="SFO",
            destination_airport="BUR",
            departure_date=date(2026, 6, 10),
            departure_time="19:40",
            arrival_time="21:05",
            booked_price=58.40,
            record_locator="",
        ),
    )
    assert booking is None
    assert unmatched is not None

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert 'name="trip_label" value="SFO to BUR"' in dashboard.text
    assert f'Booking {unmatched.unmatched_booking_id}' not in dashboard.text

    form_page = client.get(f"/trips/new?unmatched_booking_id={unmatched.unmatched_booking_id}")
    assert form_page.status_code == 200
    assert "Starting from Imported booking." in form_page.text
    assert 'name="label" value="SFO to BUR"' in form_page.text
    assert f"Starting from booking {unmatched.unmatched_booking_id}." not in form_page.text


def test_trip_creation_and_booking_flow(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
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

    trip_instance_id = Repository(settings).load_trip_instances()[0].trip_instance_id
    booking_page = client.get(f"/bookings/new?trip_instance_id={trip_instance_id}")
    assert booking_page.status_code == 200
    assert "Add booking" in booking_page.text
    assert "Scheduled trip" not in booking_page.text
    assert ">Trip<" in booking_page.text

    booking_response = client.post(
        "/bookings",
        data={
            "trip_instance_id": trip_instance_id,
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

    dashboard_page = client.get("/")
    assert "ABC123" not in dashboard_page.text

    repository = Repository(settings)
    booking = repository.load_bookings()[0]
    trip_page = client.get(f"/trip-instances/{booking.trip_instance_id}")
    assert "ABC123" in trip_page.text


def test_group_creation_and_detail_flow(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    create = client.post(
        "/groups",
        data={
            "label": "Work Trips",
            "description": "Repeated travel tied to commuting and office visits.",
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    assert create.headers["location"].startswith("/groups/")

    detail = client.get(create.headers["location"])
    assert detail.status_code == 200
    assert "Work Trips" in detail.text
    assert "Rules" in detail.text
    assert "Trips" in detail.text


def test_today_page_surfaces_planned_booked_and_unmatched_items(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    create_planned = client.post(
        "/trips",
        data={
            "label": "Planned Commute",
            "trip_kind": "one_time",
            "anchor_date": (date.today() + timedelta(days=3)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create_planned.status_code == 303

    create_booked = client.post(
        "/trips",
        data={
            "label": "Booked Commute",
            "trip_kind": "one_time",
            "anchor_date": (date.today() + timedelta(days=5)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create_booked.status_code == 303

    booked_response = client.post(
        "/bookings",
        data={
            "trip_instance_id": "",
            "airline": "Alaska",
            "origin_airport": "BUR",
            "destination_airport": "SFO",
            "departure_date": (date.today() + timedelta(days=5)).isoformat(),
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "BOOK123",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert booked_response.status_code == 303

    unmatched_response = client.post(
        "/bookings",
        data={
            "trip_instance_id": "",
            "airline": "Southwest",
            "origin_airport": "LAX",
            "destination_airport": "LAS",
            "departure_date": (date.today() + timedelta(days=8)).isoformat(),
            "departure_time": "09:15",
            "arrival_time": "10:30",
            "booked_price": "89",
            "record_locator": "UNMATCH1",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert unmatched_response.status_code == 303

    page = client.get("/")
    assert page.status_code == 200
    assert "Milemark" in page.text
    assert "Needs attention" in page.text
    assert "Upcoming trips" in page.text
    assert "Planned Commute" in page.text
    assert "Booked Commute" in page.text
    assert "Link booking" in page.text
    assert "/bookings/unmatched/" in page.text


def test_today_page_surfaces_near_term_multiple_bookings(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    trip_response = client.post(
        "/trips",
        data={
            "label": "Crowded Commute",
            "trip_kind": "one_time",
            "anchor_date": (date.today() + timedelta(days=4)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert trip_response.status_code == 303

    for record_locator, booked_price in [("MULTI1", "119"), ("MULTI2", "129")]:
        booking_response = client.post(
            "/bookings",
            data={
                "trip_instance_id": "",
                "airline": "Alaska",
                "origin_airport": "BUR",
                "destination_airport": "SFO",
                "departure_date": (date.today() + timedelta(days=4)).isoformat(),
                "departure_time": "07:10",
                "arrival_time": "08:35",
                "booked_price": booked_price,
                "record_locator": record_locator,
                "notes": "",
            },
            follow_redirects=False,
        )
        assert booking_response.status_code == 303

    page = client.get("/")
    assert page.status_code == 200
    assert "Multiple bookings" in page.text
    assert "Crowded Commute" in page.text
    assert "2 active" in page.text


def test_today_page_respects_configured_attention_windows(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    repository = Repository(settings)
    repository.save_app_state(
        AppState(
            dashboard_needs_booking_window_weeks=1,
            dashboard_overbooked_window_days=2,
        )
    )
    client = TestClient(create_app(settings))

    planned_response = client.post(
        "/trips",
        data={
            "label": "Farther Planned Trip",
            "trip_kind": "one_time",
            "anchor_date": (date.today() + timedelta(days=10)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert planned_response.status_code == 303

    overbooked_response = client.post(
        "/trips",
        data={
            "label": "Farther Overbooked Trip",
            "trip_kind": "one_time",
            "anchor_date": (date.today() + timedelta(days=4)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert overbooked_response.status_code == 303

    for record_locator, booked_price in [("CFG1", "119"), ("CFG2", "129")]:
        booking_response = client.post(
            "/bookings",
            data={
                "trip_instance_id": "",
                "airline": "Alaska",
                "origin_airport": "BUR",
                "destination_airport": "SFO",
                "departure_date": (date.today() + timedelta(days=4)).isoformat(),
                "departure_time": "07:10",
                "arrival_time": "08:35",
                "booked_price": booked_price,
                "record_locator": record_locator,
                "notes": "",
            },
            follow_redirects=False,
        )
        assert booking_response.status_code == 303

    page = client.get("/")
    assert page.status_code == 200
    assert "Book upcoming trips" not in page.text
    assert "Resolve multiple bookings" not in page.text


def test_new_weekly_rule_without_groups_creates_matching_group(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/trips",
        data={
            "label": "Commute Rule",
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "trip_group_ids_json": "[]",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    repository = Repository(settings)
    rule = next(item for item in repository.load_trips() if item.label == "Commute Rule")
    groups = repository.load_trip_groups()
    matching_group = next(item for item in groups if item.label == "Commute Rule")
    targets = repository.load_rule_group_targets()

    assert any(target.rule_trip_id == rule.trip_id and target.trip_group_id == matching_group.trip_group_id for target in targets)


def test_edit_grouped_weekly_rule_cannot_clear_all_groups(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    repository = Repository(settings)
    group = save_trip_group(repository, trip_group_id=None, label="Work trips")
    rule = save_trip(
        repository,
        trip_id=None,
        label="Work commute rule",
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

    client = TestClient(create_app(settings))
    response = client.post(
        "/trips",
        data={
            "trip_id": rule.trip_id,
            "label": rule.label,
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "trip_group_ids_json": "[]",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
    )

    assert response.status_code == 400
    assert "Recurring rules must stay in at least one group." in response.text
    assert any(target.rule_trip_id == rule.trip_id for target in repository.load_rule_group_targets())


def test_booking_can_be_unlinked_from_ui(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    create = client.post(
        "/trips",
        data={
            "label": "Unlink Booking Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    save = client.post(
        "/bookings",
        data={
            "trip_instance_id": "",
            "airline": "Alaska",
            "origin_airport": "BUR",
            "destination_airport": "SFO",
            "departure_date": "2026-04-06",
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "UNLINK123",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert save.status_code == 303

    repository = Repository(settings)
    booking = repository.load_bookings()[0]

    unlink = client.post(
        f"/bookings/{booking.booking_id}/unlink",
        headers={"referer": "/bookings"},
        follow_redirects=False,
    )
    assert unlink.status_code == 303
    assert unlink.headers["location"].startswith("/?message=Booking+needs+linking#needs-linking")

    repository = Repository(settings)
    assert not repository.load_bookings()
    unmatched = repository.load_unmatched_bookings()
    assert len(unmatched) == 1
    assert unmatched[0].record_locator == "UNLINK123"

    trips_page = client.get("/trips?q=Unlink+Booking+Trip")
    assert "UNLINK123" in trips_page.text
    assert "Link booking" in trips_page.text


def test_unlinked_booking_can_be_deleted_from_dashboard(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    save = client.post(
        "/bookings",
        data={
            "trip_instance_id": "",
            "airline": "Alaska",
            "origin_airport": "BUR",
            "destination_airport": "SFO",
            "departure_date": "2026-04-06",
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "DELETEUNLINK",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert save.status_code == 303

    repository = Repository(settings)
    unmatched = repository.load_unmatched_bookings()
    assert len(unmatched) == 1

    delete = client.post(
        f"/bookings/{unmatched[0].booking_id}/delete",
        headers={"referer": "http://testserver/#needs-linking"},
        follow_redirects=False,
    )
    assert delete.status_code == 303
    assert delete.headers["location"] == "/?message=Booking+deleted"

    repository = Repository(settings)
    assert repository.load_unmatched_bookings() == []


def test_past_active_bookings_are_not_exposed_as_a_top_level_dashboard_surface(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    past_date = date.today() - timedelta(days=3)
    create = client.post(
        "/trips",
        data={
            "label": "Past Booking Trip",
            "trip_kind": "one_time",
            "anchor_date": past_date.isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    save = client.post(
        "/bookings",
        data={
            "trip_instance_id": "",
            "airline": "Alaska",
            "origin_airport": "BUR",
            "destination_airport": "SFO",
            "departure_date": past_date.isoformat(),
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "PAST01",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert save.status_code == 303

    page = client.get("/")
    assert page.status_code == 200
    assert "PAST01" not in page.text

    repository = Repository(settings)
    booking = repository.load_bookings()[0]
    detail = client.get(f"/trip-instances/{booking.trip_instance_id}")
    assert detail.status_code == 200
    assert "PAST01" in detail.text


def test_one_time_trip_delete_removes_trip_from_user_visible_ui(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    create = client.post(
        "/trips",
        data={
            "label": "Archive UI Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    trip_detail_url = create.headers["location"].split("?", 1)[0]
    trip_id = trip_detail_url.rsplit("/", 1)[1]

    archive = client.post(f"/trips/{trip_id}/delete", follow_redirects=False)
    assert archive.status_code == 303
    assert archive.headers["location"] == "/?message=Trip+deleted#all-travel"

    trips_page = client.get("/trips")
    assert "Archive UI Trip" not in trips_page.text
    assert "Show archived" not in trips_page.text
    assert "Archived one-time trips" not in trips_page.text

    scheduled_results = client.get("/trips?partial=scheduled-results")
    assert "Archive UI Trip" not in scheduled_results.text

    deleted_trip_page = client.get(f"/trips/{trip_id}")
    assert deleted_trip_page.status_code == 404


def test_trip_creation_queues_refresh_targets_immediately(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
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
        config_dir=tmp_path / "config",
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
    assert "Needs $50 more savings to outrank higher options." in detail.text


def test_trip_creation_persists_exclude_basic_policy(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/trips",
        data={
            "label": "Exclude Basic UI Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-13",
            "anchor_weekday": "",
            "route_options_json": (
                '[{"origin_airports":["LAX"],"destination_airports":["SFO"],"airlines":["Alaska","Southwest"],'
                '"day_offset":0,"start_time":"06:00","end_time":"08:00","fare_class_policy":"exclude_basic"}]'
            ),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    repository = Repository(settings)
    route_option = repository.load_route_options()[0]
    tracker = repository.load_trackers()[0]

    assert route_option.fare_class_policy == "exclude_basic"
    assert tracker.fare_class_policy == "exclude_basic"

    detail = client.get(response.headers["location"])
    assert detail.status_code == 200
    assert "Excludes Basic fares" in detail.text


def test_edit_trip_validation_error_preserves_edit_context(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    first = client.post(
        "/trips",
        data={
            "label": "Original Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    second = client.post(
        "/trips",
        data={
            "label": "Conflict Trip",
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["LAX"],"destination_airports":["SEA"],"airlines":["Delta"],"day_offset":0,"start_time":"07:00","end_time":"11:00"}]',
        },
        follow_redirects=False,
    )
    assert first.status_code == 303
    assert second.status_code == 303

    trip_id = first.headers["location"].split("/trips/")[1].split("?")[0]
    response = client.post(
        "/trips",
        data={
            "trip_id": trip_id,
            "label": "Conflict Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "preference_mode": "equal",
            "route_options_json": '[{"route_option_id":"opt_existing","origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Trip not saved." in response.text
    assert "This Trip Label is already used by a recurring trip." in response.text
    assert "Conflict Trip" in response.text
    assert f'name=\"trip_id\" value=\"{trip_id}\"' in response.text


def test_booking_save_redirects_to_trip_instance_detail(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
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
    assert "Edit trip" in detail.text
    assert "View plan" not in detail.text


def test_edit_booking_can_leave_it_linked_but_untracked(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)

    create = client.post(
        "/trips",
        data={
            "label": "Edit Booking Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id

    save = client.post(
        "/bookings",
        data={
            "trip_instance_id": trip_instance_id,
            "airline": "Alaska",
            "origin_airport": "BUR",
            "destination_airport": "SFO",
            "departure_date": "2026-04-06",
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "EDIT01",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert save.status_code == 303
    booking = next(item for item in repository.load_bookings() if item.record_locator == "EDIT01")

    edit_page = client.get(f"/bookings/{booking.booking_id}/edit")
    assert edit_page.status_code == 200
    assert "Edit booking" in edit_page.text
    assert "Scheduled trip" not in edit_page.text

    edited = client.post(
        "/bookings",
        data={
            "booking_id": booking.booking_id,
            "trip_instance_id": trip_instance_id,
            "airline": "Alaska",
            "origin_airport": "LAX",
            "destination_airport": "SFO",
            "departure_date": "2026-04-06",
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "EDIT01",
            "notes": "Changed airport",
        },
        follow_redirects=False,
    )
    assert edited.status_code == 303
    assert edited.headers["location"].startswith("/trip-instances/")

    updated_booking = next(item for item in repository.load_bookings() if item.booking_id == booking.booking_id)
    assert updated_booking.trip_instance_id == trip_instance_id
    assert updated_booking.route_option_id == ""

    detail = client.get(edited.headers["location"])
    assert detail.status_code == 200
    assert "No tracked route match" in detail.text
    assert "does not match any tracked route on this date yet" in detail.text


def test_cancelling_booking_returns_trip_to_planned(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)

    create = client.post(
        "/trips",
        data={
            "label": "Cancel Booking Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id

    client.post(
        "/bookings",
        data={
            "trip_instance_id": trip_instance_id,
            "airline": "Alaska",
            "origin_airport": "BUR",
            "destination_airport": "SFO",
            "departure_date": "2026-04-06",
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "CANCEL1",
            "notes": "",
        },
        follow_redirects=False,
    )
    booking = next(item for item in repository.load_bookings() if item.record_locator == "CANCEL1")

    cancel = client.post(
        f"/bookings/{booking.booking_id}/cancel",
        headers={"referer": f"http://testserver/trip-instances/{trip_instance_id}"},
        follow_redirects=False,
    )
    assert cancel.status_code == 303
    assert "Booking+cancelled" in cancel.headers["location"]

    snapshot_page = client.get(f"/trip-instances/{trip_instance_id}")
    assert snapshot_page.status_code == 200
    assert ">Planned<" in snapshot_page.text
    assert ">cancelled<" in snapshot_page.text


def test_restoring_cancelled_booking_returns_trip_to_booked(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)

    client.post(
        "/trips",
        data={
            "label": "Restore Booking Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id

    client.post(
        "/bookings",
        data={
            "trip_instance_id": trip_instance_id,
            "airline": "Alaska",
            "origin_airport": "BUR",
            "destination_airport": "SFO",
            "departure_date": "2026-04-06",
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "RESTORE1",
            "notes": "",
        },
        follow_redirects=False,
    )
    booking = next(item for item in repository.load_bookings() if item.record_locator == "RESTORE1")

    client.post(
        f"/bookings/{booking.booking_id}/cancel",
        headers={"referer": f"http://testserver/trip-instances/{trip_instance_id}"},
        follow_redirects=False,
    )

    restore = client.post(
        f"/bookings/{booking.booking_id}/restore",
        headers={"referer": f"http://testserver/trip-instances/{trip_instance_id}"},
        follow_redirects=False,
    )
    assert restore.status_code == 303
    assert "Booking+restored" in restore.headers["location"]

    restored_booking = next(item for item in repository.load_bookings() if item.booking_id == booking.booking_id)
    assert restored_booking.status == "active"

    snapshot_page = client.get(f"/trip-instances/{trip_instance_id}")
    assert snapshot_page.status_code == 200
    assert ">Booked<" in snapshot_page.text
    assert ">active<" in snapshot_page.text


def test_deleting_booking_removes_it_and_recomputes_trip_state(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)

    create = client.post(
        "/trips",
        data={
            "label": "Delete Booking Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id
    client.post(
        "/bookings",
        data={
            "trip_instance_id": trip_instance_id,
            "airline": "Alaska",
            "origin_airport": "BUR",
            "destination_airport": "SFO",
            "departure_date": "2026-04-06",
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "DELETE1",
            "notes": "",
        },
        follow_redirects=False,
    )
    booking = next(item for item in repository.load_bookings() if item.record_locator == "DELETE1")

    delete = client.post(
        f"/bookings/{booking.booking_id}/delete",
        headers={"referer": "http://testserver/bookings"},
        follow_redirects=False,
    )
    assert delete.status_code == 303
    assert delete.headers["location"] == "/?message=Booking+deleted#needs-linking"
    assert repository.load_bookings() == []

    detail = client.get(f"/trip-instances/{trip_instance_id}")
    assert detail.status_code == 200
    assert ">Planned<" in detail.text


def test_editing_trip_surfaces_warning_when_linked_bookings_stop_matching_routes(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)

    create = client.post(
        "/trips",
        data={
            "label": "Warning Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "preference_mode": "equal",
            "route_options_json": '[{"route_option_id":"opt_warning","origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    trip_id = create.headers["location"].split("/trips/")[1].split("?", 1)[0]
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id
    client.post(
        "/bookings",
        data={
            "trip_instance_id": trip_instance_id,
            "airline": "Alaska",
            "origin_airport": "BUR",
            "destination_airport": "SFO",
            "departure_date": "2026-04-06",
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "WARN01",
            "notes": "",
        },
        follow_redirects=False,
    )

    edit = client.post(
        "/trips",
        data={
            "trip_id": trip_id,
            "label": "Warning Trip",
            "trip_kind": "one_time",
            "trip_group_ids_json": "[]",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "preference_mode": "equal",
            "route_options_json": '[{"route_option_id":"opt_warning","origin_airports":["LAX"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00","fare_class_policy":"include_basic","savings_needed_vs_previous":0}]',
        },
        follow_redirects=False,
    )
    assert edit.status_code == 303
    assert "linked+booking+does+not+match+a+unique+tracked+route" in edit.headers["location"]

    booking = next(item for item in repository.load_bookings() if item.record_locator == "WARN01")
    assert booking.route_option_id == ""


def test_group_delete_requires_rules_to_be_removed_first(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    group = save_trip_group(repository, trip_group_id=None, label="Delete Protected Group")

    client.post(
        "/trips",
        data={
            "label": "Protected Rule",
            "trip_kind": "weekly",
            "trip_group_ids_json": json.dumps([group.trip_group_id]),
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )

    delete = client.post(
        f"/groups/{group.trip_group_id}/delete",
        headers={"referer": f"http://testserver/groups/{group.trip_group_id}"},
        follow_redirects=False,
    )
    assert delete.status_code == 303
    assert "Remove+or+retarget+recurring+rules+before+deleting+this+group." in delete.headers["location"]
    assert any(item.trip_group_id == group.trip_group_id for item in repository.load_trip_groups())


def test_group_delete_removes_manual_memberships(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    group = save_trip_group(repository, trip_group_id=None, label="Delete Manual Group")

    create = client.post(
        "/trips",
        data={
            "label": "Grouped One-Off",
            "trip_kind": "one_time",
            "trip_group_ids_json": json.dumps([group.trip_group_id]),
            "anchor_date": "2026-05-10",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["LAX"],"destination_airports":["SEA"],"airlines":["Delta"],"day_offset":0,"start_time":"07:00","end_time":"11:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    assert any(item.trip_group_id == group.trip_group_id for item in repository.load_trip_groups())
    assert any(item.trip_group_id == group.trip_group_id for item in repository.load_trip_instance_group_memberships())

    delete = client.post(
        f"/groups/{group.trip_group_id}/delete",
        headers={"referer": f"http://testserver/groups/{group.trip_group_id}"},
        follow_redirects=False,
    )
    assert delete.status_code == 303
    assert delete.headers["location"] == "/?message=Trip+group+deleted#dashboard-groups"
    assert all(item.trip_group_id != group.trip_group_id for item in repository.load_trip_groups())
    assert all(item.trip_group_id != group.trip_group_id for item in repository.load_trip_instance_group_memberships())


def test_trip_instance_detail_renders_multiple_linked_bookings(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/trips",
        data={
            "label": "Multi Booking Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    trip_instance_url = response.headers["location"]
    trip_instance_id = trip_instance_url.rsplit("/", 1)[1].split("?", 1)[0]

    for locator in ["MULTI1", "MULTI2"]:
        booking_response = client.post(
            "/bookings",
            data={
                "trip_instance_id": trip_instance_id,
                "airline": "Alaska",
                "origin_airport": "BUR",
                "destination_airport": "SFO",
                "departure_date": "2026-04-06",
                "departure_time": "07:10",
                "arrival_time": "08:35",
                "booked_price": "119",
                "record_locator": locator,
                "notes": "",
            },
            follow_redirects=False,
        )
        assert booking_response.status_code == 303

    detail = client.get(trip_instance_url)
    assert detail.status_code == 200
    assert "Bookings" in detail.text
    assert "MULTI1" in detail.text
    assert "MULTI2" in detail.text
    assert "2 active" in detail.text


def test_pause_and_activate_trip_redirect_to_trips_by_default(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
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
    assert pause.headers["location"] == "/?message=Trip+paused#all-travel"

    activate = client.post(f"/trips/{trip_id}/activate", follow_redirects=False)
    assert activate.status_code == 303
    assert (
        activate.headers["location"]
        == "/?message=Trip+activated.+Refresh+queued+for+16+airport-pair+searches.#all-travel"
    )

    pause_from_page = client.post(
        f"/trips/{trip_id}/pause",
        headers={"referer": "http://testserver/trips?q=Test+Weekly+Trip"},
        follow_redirects=False,
    )
    assert pause_from_page.status_code == 303
    assert pause_from_page.headers["location"] == "/?q=Test+Weekly+Trip&message=Trip+paused#all-travel"

    activate_from_page = client.post(
        f"/trips/{trip_id}/activate",
        headers={"referer": "http://testserver/trips?q=Test+Weekly+Trip"},
        follow_redirects=False,
    )
    assert activate_from_page.status_code == 303
    assert (
        activate_from_page.headers["location"]
        == "/?q=Test+Weekly+Trip&message=Trip+activated.+Refresh+queued+for+16+airport-pair+searches.#all-travel"
    )


def test_trip_activation_queues_refresh_targets_immediately(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
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
    assert "Trip+activated.+Refresh+queued+for+16+airport-pair+searches." in activate.headers["location"]

    refreshed_targets = repository.load_tracker_fetch_targets()
    assert len(refreshed_targets) == 16
    assert all(target.next_fetch_not_before is not None for target in refreshed_targets)
    assert all(target.next_fetch_not_before < delayed_until for target in refreshed_targets)


def test_trips_page_separates_recurring_plans_from_scheduled_trips(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
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
    assert "Collections" in trips_page.text
    assert "Search trips" in trips_page.text
    assert "Weekly LA to SF" in trips_page.text
    assert "Conference Arrival" in trips_page.text
    assert "Show in scheduled" not in trips_page.text
    assert "Log past trip" not in trips_page.text
    assert "Past trips" not in trips_page.text


def test_deleted_generated_occurrence_disappears_from_scheduled_lists(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    create = client.post(
        "/trips",
        data={
            "label": "Doctor Visit Rule",
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Sunday",
            "route_options_json": '[{"origin_airports":["LAX"],"destination_airports":["SEA"],"airlines":["Delta"],"day_offset":0,"start_time":"07:00","end_time":"11:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    trips_page = client.get(f"/trips?q=Doctor+Visit+Rule")
    assert trips_page.status_code == 200
    marker = 'id="scheduled-'
    assert marker in trips_page.text
    trip_instance_id = trips_page.text.split(marker, 1)[1].split('"', 1)[0]

    delete_response = client.post(
        f"/trip-instances/{trip_instance_id}/delete-generated",
        headers={"referer": "http://testserver/trips?q=Doctor+Visit+Rule"},
        follow_redirects=False,
    )
    assert delete_response.status_code == 303
    assert delete_response.headers["location"].startswith("/groups/")
    assert delete_response.headers["location"].endswith("?message=Trip+deleted")

    trips_page = client.get("/trips")
    assert trips_page.status_code == 200
    assert "Doctor Visit Rule" in trips_page.text
    assert "No scheduled trips match these filters." not in trips_page.text
    filtered_page = client.get("/trips?q=Doctor+Visit+Rule")
    assert filtered_page.status_code == 200
    assert f'id="scheduled-{trip_instance_id}"' not in filtered_page.text


def test_recurring_trip_group_detail_shows_deleted_occurrence_as_removed(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    group = save_trip_group(repository, trip_group_id=None, label="Weekly commute")

    create = client.post(
        "/trips",
        data={
            "label": "Weekly Commute",
            "trip_kind": "weekly",
            "trip_group_ids_json": json.dumps([group.trip_group_id]),
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    trip_location = create.headers["location"]
    trip_id = trip_location.split("/trips/")[1].split("?")[0]
    trip = next(item for item in repository.load_trips() if item.trip_id == trip_id)
    assert any(
        target.rule_trip_id == trip.trip_id and target.trip_group_id == group.trip_group_id
        for target in repository.load_rule_group_targets()
    )
    trips_page = client.get(f"/trips?trip_group_id={group.trip_group_id}")
    assert trips_page.status_code == 200
    marker = 'id="scheduled-'
    assert marker in trips_page.text
    trip_instance_id = trips_page.text.split(marker, 1)[1].split('"', 1)[0]

    delete_response = client.post(
        f"/trip-instances/{trip_instance_id}/delete-generated",
        headers={"referer": f"http://testserver/trips?trip_group_id={group.trip_group_id}"},
        follow_redirects=False,
    )
    assert delete_response.status_code == 303
    assert delete_response.headers["location"] == f"/groups/{group.trip_group_id}?message=Trip+deleted"

    group_page = client.get(f"/groups/{group.trip_group_id}")
    assert group_page.status_code == 200
    assert "Weekly Commute" in group_page.text
    assert group_page.text.count('class="card scheduled-card"') == 15


def test_trip_detail_renders_real_trip_page(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
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
    assert "Routes" in response.text
    assert "Trips" in response.text


def test_one_time_trip_detail_redirects_to_scheduled_trip_page(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    create = client.post(
        "/trips",
        data={
            "label": "Redirect One-Time Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    trip_id = create.headers["location"].split("/trips/")[1].split("?")[0]

    response = client.get(f"/trips/{trip_id}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/trip-instances/")


def test_one_time_trip_delete_uses_app_confirm_modal_markup(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    create = client.post(
        "/trips",
        data={
            "label": "Modal Delete Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    detail = client.get(create.headers["location"])
    assert detail.status_code == 200
    assert 'data-confirm-title="Delete this one-time trip?"' in detail.text
    assert 'data-confirm-action="Delete trip"' in detail.text
    assert "return confirm(" not in detail.text


def test_scheduled_trips_can_be_filtered_to_specific_recurring_parents(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    work_group = save_trip_group(repository, trip_group_id=None, label="Work Travel")

    weekly_one = client.post(
        "/trips",
        data={
            "label": "Weekly Commute A",
            "trip_kind": "weekly",
            "trip_group_ids_json": json.dumps([work_group.trip_group_id]),
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
    weekly_one_trip = next(item for item in repository.load_trips() if item.trip_id == weekly_one_id)
    assert any(
        target.rule_trip_id == weekly_one_trip.trip_id and target.trip_group_id == work_group.trip_group_id
        for target in repository.load_rule_group_targets()
    )

    filtered_page = client.get(f"/?partial=scheduled-results&trip_group_id={work_group.trip_group_id}")
    assert filtered_page.status_code == 200
    assert "Weekly Commute A" in filtered_page.text
    assert "One-off Flight" not in filtered_page.text


def test_editing_grouped_rule_cannot_remove_all_target_groups(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    work_group = save_trip_group(repository, trip_group_id=None, label="Work Travel")

    create = client.post(
        "/trips",
        data={
            "label": "Weekly Commute A",
            "trip_kind": "weekly",
            "trip_group_ids_json": json.dumps([work_group.trip_group_id]),
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "preference_mode": "equal",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00","fare_class_policy":"include_basic","savings_needed_vs_previous":0}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    trip_id = create.headers["location"].split("/trips/")[1].split("?")[0]

    edit = client.post(
        "/trips",
        data={
            "trip_id": trip_id,
            "label": "Weekly Commute A",
            "trip_kind": "weekly",
            "trip_group_ids_json": json.dumps([]),
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "preference_mode": "equal",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00","fare_class_policy":"include_basic","savings_needed_vs_previous":0}]',
        },
        follow_redirects=True,
    )
    assert edit.status_code == 400
    assert "Recurring rules must stay in at least one group." in edit.text

    assert [
        (item.rule_trip_id, item.trip_group_id)
        for item in repository.load_rule_group_targets()
        if item.rule_trip_id == trip_id
    ] == [(trip_id, work_group.trip_group_id)]

    group_page = client.get(f"/groups/{work_group.trip_group_id}")
    assert group_page.status_code == 200
    assert "Weekly Commute A" in group_page.text


def test_scheduled_partial_renders_live_filter_surface(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
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

    partial = client.get("/?partial=scheduled")
    assert partial.status_code == 200
    assert 'data-scheduled-filter-form' in partial.text
    assert "Show skipped" not in partial.text
    assert "Apply filters" in partial.text


def test_past_trips_are_hidden_from_the_trips_ui(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
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
        config_dir=tmp_path / "config",
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
    assert "Tracked searches" in trackers_page.text
    assert "Last updated:" in trackers_page.text
    assert "Next refresh:" in trackers_page.text
    assert "BUR to SFO" in trackers_page.text
    assert "LAX to SFO" in trackers_page.text


def test_trip_trackers_page_can_queue_a_rolling_refresh(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
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
        config_dir=tmp_path / "config",
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
    assert "A recent Google Flights request failed. Milemark will retry automatically." not in trackers_page.text
    assert "is-unavailable" in trackers_page.text


def test_unmatched_booking_can_be_linked_from_bookings_page(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
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
    assert booking_response.headers["location"] == "/?message=Booking+needs+linking#needs-linking"

    dashboard_page = client.get("/")
    unmatched_id = dashboard_page.text.split('/bookings/unmatched/', 1)[1].split('/link', 1)[0]

    trips_page = client.get("/trips?q=Resolve+Redirect+Trip")
    trip_instance_id = trips_page.text.split('href="/trip-instances/', 1)[1].split('"', 1)[0]
    resolve_response = client.post(
        f"/bookings/unmatched/{unmatched_id}/link",
        data={"trip_instance_id": trip_instance_id},
        follow_redirects=False,
    )
    assert resolve_response.status_code == 303
    assert resolve_response.headers["location"].startswith("/trip-instances/")


def test_unmatched_booking_dropdown_separates_past_trips(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    today = date.today()

    for label, anchor_date in (
        ("Past Choice", (today - timedelta(days=1)).isoformat()),
        ("Upcoming Choice", (today + timedelta(days=3)).isoformat()),
    ):
        create = client.post(
            "/trips",
            data={
                "label": label,
                "trip_kind": "one_time",
                "anchor_date": anchor_date,
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
            "airline": "United",
            "origin_airport": "LAX",
            "destination_airport": "SEA",
            "departure_date": (today + timedelta(days=8)).isoformat(),
            "departure_time": "09:10",
            "arrival_time": "11:35",
            "booked_price": "199",
            "record_locator": "PASTOPT",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert booking_response.status_code == 303

    page = client.get("/")
    assert "Past trips" in page.text
    assert "Upcoming trips" in page.text


def test_past_trips_remain_hidden_from_filtered_scheduled_lists(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    today = date.today()

    create = client.post(
        "/trips",
        data={
            "label": "Hide me later",
            "trip_kind": "one_time",
            "anchor_date": (today - timedelta(days=1)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    trips_page = client.get("/trips?q=Hide+me+later")
    assert 'id="past-' not in trips_page.text
    assert "Showing 0 scheduled trips." in trips_page.text
    assert "No scheduled trips match these filters." in trips_page.text


def test_linked_booking_warning_appears_when_no_route_matches(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    repository = Repository(settings)
    trip = save_trip(
        repository,
        trip_id=None,
        label="Warning Trip",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 20),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SEA",
                "airlines": "Delta",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    from app.services.workflows import sync_and_persist

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance_id = next(item.trip_instance_id for item in snapshot.trip_instances if item.trip_id == trip.trip_id)
    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Alaska",
            origin_airport="BUR",
            destination_airport="SFO",
            departure_date=date(2026, 4, 20),
            departure_time="07:15",
            arrival_time="08:40",
            booked_price=121,
            record_locator="WARN01",
        ),
        trip_instance_id=trip_instance_id,
    )
    assert booking is not None
    assert unmatched is None
    sync_and_persist(repository, today=date(2026, 4, 1))

    client = TestClient(create_app(settings))
    detail = client.get(f"/trip-instances/{trip_instance_id}")

    assert detail.status_code == 200
    assert "No tracked route match" in detail.text
    assert "does not match any tracked route on this date yet" in detail.text
