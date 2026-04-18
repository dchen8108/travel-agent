from __future__ import annotations

import json
from decimal import Decimal
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.base import AppState
from app.models.base import FetchTargetStatus, utcnow
from app.services.dashboard_navigation import trip_focus_url
from app.services.bookings import BookingCandidate, record_booking
from app.services.groups import save_trip_group
from app.services.trip_instances import detach_generated_trip_instance
from app.services.trips import save_trip
from app.services.workflows import sync_and_persist
from app.settings import Settings
from app.storage.repository import Repository


def _trip_by_label(repository: Repository, label: str):
    return next(item for item in repository.load_trips() if item.label == label)


def _trip_instance_id_for_trip(repository: Repository, trip_id: str) -> str:
    return next(item.trip_instance_id for item in repository.load_trip_instances() if item.trip_id == trip_id)


def _trip_instance_id_for_label(repository: Repository, label: str) -> str:
    return _trip_instance_id_for_trip(repository, _trip_by_label(repository, label).trip_id)


def _dashboard_payload(client: TestClient, **params: object) -> dict[str, object]:
    response = client.get("/api/dashboard", params=params)
    assert response.status_code == 200
    return response.json()


def _booking_panel_payload(
    client: TestClient,
    trip_instance_id: str,
    *,
    mode: str = "list",
    booking_id: str = "",
) -> dict[str, object]:
    response = client.get(
        f"/api/trip-instances/{trip_instance_id}/bookings",
        params={"mode": mode, "booking_id": booking_id} if booking_id else {"mode": mode},
    )
    assert response.status_code == 200
    return response.json()


def _tracker_panel_payload(client: TestClient, trip_instance_id: str) -> dict[str, object]:
    response = client.get(f"/api/trip-instances/{trip_instance_id}/trackers")
    assert response.status_code == 200
    return response.json()


def test_core_pages_render(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    for path in ["/", "/trips", "/trips/new", "/bookings", "/trackers"]:
        response = client.get(path)
        assert response.status_code == 200
    root_page = client.get("/")
    assert '<div id="root"></div>' in root_page.text
    trips_redirect = client.get("/trips", follow_redirects=False)
    assert trips_redirect.status_code == 303
    assert trips_redirect.headers["location"] == "/#all-travel"
    bookings_redirect = client.get("/bookings", follow_redirects=False)
    assert bookings_redirect.status_code == 303
    assert bookings_redirect.headers["location"] == "/#needs-linking"
    new_booking_redirect = client.get("/bookings/new", follow_redirects=False)
    assert new_booking_redirect.status_code == 303
    assert "Start+from+a+trip+to+add+a+booking." in new_booking_redirect.headers["location"]
    new_group_page = client.get("/groups/new", follow_redirects=False)
    assert new_group_page.status_code == 303
    assert new_group_page.headers["location"] == "/?create_group=1#dashboard-groups"
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
    assert '<div id="root"></div>' in form_page.text

    form_payload = client.get(
        "/api/trips/new-form",
        params={
            "unmatched_booking_id": unmatched.unmatched_booking_id,
            "trip_label": "Conference Arrival",
        },
    )
    assert form_payload.status_code == 200
    payload = form_payload.json()
    assert payload["sourceBooking"]["referenceLabel"] == "Booking ZZZ999"
    assert payload["values"]["label"] == "Conference Arrival"
    assert payload["routeOptions"][0]["originAirports"] == ["LAX"]
    assert payload["routeOptions"][0]["destinationAirports"] == ["SEA"]

    save = client.post(
        "/api/trips/editor",
        json={
            **payload["values"],
            "routeOptions": payload["routeOptions"],
            "sourceUnmatchedBookingId": unmatched.unmatched_booking_id,
        },
    )
    assert save.status_code == 200
    trip = _trip_by_label(repository, "Conference Arrival")
    trip_instance_id = _trip_instance_id_for_trip(repository, trip.trip_id)
    assert "panel=bookings" in save.json()["redirectTo"]
    assert f"trip_instance_id={trip_instance_id}" in save.json()["redirectTo"]

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

    payload = _dashboard_payload(client)
    unmatched_item = next(item for item in payload["actionItems"] if item["kind"] == "unmatchedBooking")
    assert unmatched_item["title"] == "Link booking"
    assert unmatched_item["dateTile"] == {"weekday": "WED", "monthDay": "Jun 10"}
    assert f'Booking {unmatched.unmatched_booking_id}' not in json.dumps(payload)

    form_page = client.get(f"/trips/new?unmatched_booking_id={unmatched.unmatched_booking_id}")
    assert form_page.status_code == 200
    assert '<div id="root"></div>' in form_page.text
    form_payload = client.get(
        "/api/trips/new-form",
        params={"unmatched_booking_id": unmatched.unmatched_booking_id},
    )
    assert form_payload.status_code == 200
    payload = form_payload.json()
    assert payload["sourceBooking"]["referenceLabel"] == "Imported booking"
    assert payload["values"]["label"] == "SFO to BUR"
    assert f"booking {unmatched.unmatched_booking_id}" not in json.dumps(payload).lower()


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
                "anchor_date": "2026-06-06",
                "anchor_weekday": "",
                "route_options_json": '[{"origin_airports":["BUR","LAX"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    payload = _dashboard_payload(client)
    assert any(item["trip"]["title"] == "LA to SF Outbound" for item in payload["trips"])

    trip_instance_id = Repository(settings).load_trip_instances()[0].trip_instance_id
    booking_page = client.get(
        f"/trip-instances/{trip_instance_id}/bookings-panel?booking_mode=create",
        follow_redirects=False,
    )
    assert booking_page.status_code == 303
    assert f"panel=bookings&trip_instance_id={trip_instance_id}&booking_mode=create" in booking_page.headers["location"]
    booking_payload = _booking_panel_payload(client, trip_instance_id, mode="create")
    assert booking_payload["mode"] == "create"
    assert booking_payload["form"] is not None

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

    payload = _dashboard_payload(client)
    assert any(
        item["bookedOffer"] and item["bookedOffer"]["metaLabel"].endswith("ABC123")
        for item in payload["trips"]
    )


def test_unmatched_booking_does_not_preselect_unrelated_trip(tmp_path: Path) -> None:
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
            "label": "Unrelated trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-06-10",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    booking, unmatched = record_booking(
        Repository(settings),
        BookingCandidate(
            airline="Alaska",
            origin_airport="JFK",
            destination_airport="LAX",
            departure_date=date(2026, 6, 10),
            departure_time="21:30",
            arrival_time="00:45",
            booked_price=36.20,
            record_locator="SKLOAK",
        ),
    )
    assert booking is None
    assert unmatched is not None

    payload = _dashboard_payload(client)
    unmatched_item = next(item for item in payload["actionItems"] if item["kind"] == "unmatchedBooking")
    assert unmatched_item["preferredTripInstanceId"] == ""
    assert any(group["options"] for group in unmatched_item["tripOptions"])


def test_unmatched_booking_preselects_first_suggested_match(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    for label in ("Zulu match", "Alpha match"):
        create = client.post(
            "/trips",
            data={
                "label": label,
                "trip_kind": "one_time",
                "anchor_date": "2026-06-10",
                "anchor_weekday": "",
                "route_options_json": '[{"origin_airports":["JFK"],"destination_airports":["LAX"],"airlines":["Alaska"],"day_offset":0,"start_time":"20:00","end_time":"23:00"}]',
            },
            follow_redirects=False,
        )
        assert create.status_code == 303

    repository = Repository(settings)
    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Alaska",
            origin_airport="JFK",
            destination_airport="LAX",
            departure_date=date(2026, 6, 10),
            departure_time="21:30",
            arrival_time="00:45",
            booked_price=36.20,
            record_locator="MULTI01",
        ),
    )
    assert booking is None
    assert unmatched is not None

    matching_instances = sorted(
        [
            item
            for item in repository.load_trip_instances()
            if item.display_label in {"Zulu match", "Alpha match"}
        ],
        key=lambda item: (item.anchor_date, item.display_label.lower()),
    )

    payload = _dashboard_payload(client)
    unmatched_item = next(item for item in payload["actionItems"] if item["kind"] == "unmatchedBooking")
    assert unmatched_item["preferredTripInstanceId"] == matching_instances[0].trip_instance_id


def test_booking_form_picker_fields_use_field_wrappers_not_labels(tmp_path: Path) -> None:
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
            "label": "Picker Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-06-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    trip_instance_id = Repository(settings).load_trip_instances()[0].trip_instance_id
    booking_page = client.get(
        f"/trip-instances/{trip_instance_id}/bookings-panel?booking_mode=create",
        follow_redirects=False,
    )
    assert booking_page.status_code == 303
    booking_payload = _booking_panel_payload(client, trip_instance_id, mode="create")
    assert booking_payload["form"] is not None
    assert len(booking_payload["catalogs"]["airlines"]) > 0
    assert len(booking_payload["catalogs"]["airports"]) > 0


def test_trip_form_collection_picker_uses_field_wrapper_not_label(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    trip_page = client.get("/trips/new")

    assert trip_page.status_code == 200
    assert '<div id="root"></div>' in trip_page.text
    assert '"tripGroups":[' in trip_page.text
    assert "data-trip-group-label" not in trip_page.text


def test_trip_create_rejects_invalid_collection_picker_payload(tmp_path: Path) -> None:
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
            "label": "Bad Collections",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "trip_group_ids_json": "not-json",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Collections selection is invalid." in response.text


def test_trip_create_rejects_unknown_collection_picker_values(tmp_path: Path) -> None:
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
            "label": "Unknown Collections",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "trip_group_ids_json": '["grp_missing"]',
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Choose valid collections." in response.text


def test_booking_create_rejects_missing_picker_backed_fields(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/bookings",
        data={
            "trip_instance_id": "inst_missing",
            "airline": "",
            "origin_airport": "",
            "destination_airport": "",
            "departure_date": "2026-04-06",
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "ABC123",
            "notes": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert response.text == "Choose an airline."


def test_booking_create_rejects_invalid_explicit_trip_instance(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/bookings",
        data={
            "trip_instance_id": "inst_missing",
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

    assert response.status_code == 400
    assert response.text == "Choose a valid scheduled trip."


def test_booking_modal_create_keeps_validation_errors_inside_panel(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)

    save_trip(
        repository,
        trip_id=None,
        label="LA to SF Outbound",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 6, 6),
        anchor_weekday="",
        trip_group_ids=[],
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
    sync_and_persist(repository)
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id

    response = client.post(
        "/bookings",
        data={
            "trip_instance_id": trip_instance_id,
            "airline": "",
            "origin_airport": "",
            "destination_airport": "",
            "departure_date": "2026-06-06",
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "ABC123",
            "notes": "",
        },
        headers={"X-Requested-With": "fetch"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert response.text == "Choose an airline."


def test_booking_edit_rejects_unknown_explicit_booking_id(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/bookings",
        data={
            "booking_id": "book_missing",
            "trip_instance_id": "",
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

    assert response.status_code == 404
    assert response.json()["detail"] == "'Booking not found'"


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
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    group_id = Repository(settings).load_trip_groups()[0].trip_group_id
    assert create.headers["location"] == f"/?message=Collection+saved#group-{group_id}"

    payload = _dashboard_payload(client)
    assert any(item["label"] == "Work Trips" for item in payload["collections"])


def test_collection_inline_editor_validation_flow(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    group = save_trip_group(repository, trip_group_id=None, label="Commute")
    other_group = save_trip_group(repository, trip_group_id=None, label="Family")

    duplicate = client.post(
        "/groups",
        data={
            "trip_group_id": "",
            "label": "Commute",
            "cancel_url": "/#dashboard-groups",
        },
        headers={"X-Requested-With": "fetch"},
    )
    assert duplicate.status_code == 400
    assert "Group names must be unique." in duplicate.text

    edit_duplicate = client.post(
        "/groups",
        data={
            "trip_group_id": other_group.trip_group_id,
            "label": "Commute",
            "cancel_url": f"/#group-{other_group.trip_group_id}",
        },
        headers={"X-Requested-With": "fetch"},
    )
    assert edit_duplicate.status_code == 400
    assert "Group names must be unique." in edit_duplicate.text
    reloaded_other_group = next(
        item
        for item in Repository(settings).load_trip_groups()
        if item.trip_group_id == other_group.trip_group_id
    )
    assert reloaded_other_group.label == "Family"

    create = client.post(
        "/groups",
        data={
            "trip_group_id": "",
            "label": "Errands",
            "cancel_url": "/#dashboard-groups",
        },
        headers={"X-Requested-With": "fetch"},
        follow_redirects=False,
    )
    assert create.status_code == 303
    created_group = next(
        item
        for item in Repository(settings).load_trip_groups()
        if item.label == "Errands"
    )
    assert create.headers["location"] == f"/?message=Collection+saved#group-{created_group.trip_group_id}"


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

    payload = _dashboard_payload(client)
    trip_titles = [item["trip"]["title"] for item in payload["trips"]]
    assert "Planned Commute" in trip_titles
    assert "Booked Commute" in trip_titles
    assert any(item["kind"] == "unmatchedBooking" for item in payload["actionItems"])

    planned_only_payload = _dashboard_payload(client, include_booked="false")
    planned_only_titles = [item["trip"]["title"] for item in planned_only_payload["trips"]]
    assert "Planned Commute" in planned_only_titles
    assert "Booked Commute" not in planned_only_titles


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

    payload = _dashboard_payload(client)
    overbooked = [item for item in payload["actionItems"] if item.get("attentionKind") == "overbooked"]
    assert overbooked
    assert overbooked[0]["row"]["trip"]["title"] == "Crowded Commute"
    assert overbooked[0]["badge"] == "2 active"


def test_today_page_only_applies_needs_booking_window(tmp_path: Path) -> None:
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
    payload = _dashboard_payload(client)
    assert any(item.get("attentionKind") == "overbooked" for item in payload["actionItems"])


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

    payload = _dashboard_payload(client)
    unmatched_item = next(item for item in payload["actionItems"] if item["kind"] == "unmatchedBooking")
    assert unmatched_item["offer"]["metaLabel"].endswith("UNLINK123")


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
    detail = _booking_panel_payload(client, booking.trip_instance_id)
    assert any(row["offer"]["metaLabel"].endswith("PAST01") for row in detail["rows"])


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
    trip_id = _trip_by_label(Repository(settings), "Archive UI Trip").trip_id

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
    assert response.headers["location"].startswith("/?message=Trip+saved#scheduled-inst_")

    repository = Repository(settings)
    fetch_targets = repository.load_tracker_fetch_targets()
    assert len(fetch_targets) == 2
    assert all(target.refresh_requested_at is not None for target in fetch_targets)
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

    edit_page = client.get(f"/trips/{trip.trip_id}/edit")
    assert edit_page.status_code == 200
    assert '<div id="root"></div>' in edit_page.text

    form_payload = client.get(f"/api/trips/{trip.trip_id}/edit-form").json()
    assert form_payload["values"]["preferenceMode"] == "ranked_bias"
    assert form_payload["routeOptions"][1]["savingsNeededVsPrevious"] == 50


def test_trip_creation_persists_economy_fare_class(tmp_path: Path) -> None:
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

    assert route_option.fare_class == "economy"
    assert tracker.fare_class == "economy"

    trip = repository.load_trips()[0]
    edit_page = client.get(f"/trips/{trip.trip_id}/edit")
    assert edit_page.status_code == 200
    assert '<div id="root"></div>' in edit_page.text

    form_payload = client.get(f"/api/trips/{trip.trip_id}/edit-form").json()
    assert form_payload["routeOptions"][0]["fareClass"] == "economy"


def test_edit_trip_validation_error_returns_plain_error_and_preserves_trip(tmp_path: Path) -> None:
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

    trip_id = _trip_by_label(Repository(settings), "Original Trip").trip_id
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
    assert "This Trip Label is already used by a recurring trip." in response.text
    trip = _trip_by_label(Repository(settings), "Original Trip")
    assert trip.trip_id == trip_id
    assert trip.label == "Original Trip"


def test_editing_detached_trip_anchor_date_updates_same_instance(tmp_path: Path) -> None:
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
        label="Detach Edit UI",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Wednesday",
        route_option_payloads=[
            {
                "origin_airports": "SFO",
                "destination_airports": "BUR|LAX",
                "airlines": "Southwest|Alaska",
                "day_offset": 0,
                "start_time": "17:00",
                "end_time": "22:00",
            }
        ],
    )
    initial = sync_and_persist(repository, today=date(2026, 3, 31))
    generated = next(item for item in initial.trip_instances if item.trip_id == trip.trip_id)
    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Southwest",
            origin_airport="SFO",
            destination_airport="BUR",
            departure_date=generated.anchor_date + timedelta(days=1),
            departure_time="18:50",
            arrival_time="20:15",
            booked_price=Decimal("58.40"),
            record_locator="UIEDIT",
        ),
        trip_instance_id=generated.trip_instance_id,
    )
    assert booking is not None
    assert unmatched is None
    detached = detach_generated_trip_instance(repository, generated.trip_instance_id)
    refreshed = sync_and_persist(repository, today=date(2026, 3, 31))
    detached_trip = next(item for item in refreshed.trips if item.trip_id == detached.trip_id)
    route_options_json = json.dumps(
        [
            {
                "route_option_id": option.route_option_id,
                "origin_airports": option.origin_codes,
                "destination_airports": option.destination_codes,
                "airlines": option.airline_codes,
                "day_offset": option.day_offset,
                "start_time": option.start_time,
                "end_time": option.end_time,
                "fare_class": option.fare_class,
                "savings_needed_vs_previous": option.savings_needed_vs_previous,
            }
            for option in repository.load_route_options()
            if option.trip_id == detached_trip.trip_id
        ]
    )

    client = TestClient(create_app(settings))
    response = client.post(
        "/trips",
        data={
            "trip_id": detached_trip.trip_id,
            "label": detached_trip.label,
            "trip_kind": "one_time",
            "anchor_date": (generated.anchor_date + timedelta(days=1)).isoformat(),
            "anchor_weekday": "",
            "preference_mode": detached_trip.preference_mode,
            "data_scope": detached_trip.data_scope,
            "route_options_json": route_options_json,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    final_snapshot = sync_and_persist(repository, today=date(2026, 3, 31))
    detached_instances = [
        item
        for item in final_snapshot.trip_instances
        if item.trip_id == detached_trip.trip_id and not item.deleted
    ]
    assert len(detached_instances) == 1
    assert detached_instances[0].trip_instance_id == generated.trip_instance_id
    assert detached_instances[0].anchor_date == generated.anchor_date + timedelta(days=1)


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
    trip_instance_id = Repository(settings).load_trip_instances()[0].trip_instance_id
    assert "panel=bookings" in booking_response.headers["location"]
    assert f"trip_instance_id={trip_instance_id}" in booking_response.headers["location"]

    detail = client.get(f"/trip-instances/{trip_instance_id}/bookings-panel", follow_redirects=False)
    assert detail.status_code == 303
    assert f"panel=bookings&trip_instance_id={trip_instance_id}" in detail.headers["location"]
    booking_payload = _booking_panel_payload(client, trip_instance_id)
    assert booking_payload["trip"]["tripInstanceId"] == trip_instance_id
    assert any(row["offer"]["metaLabel"].endswith("BOOK01") for row in booking_payload["rows"])


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

    edit_redirect = client.get(f"/bookings/{booking.booking_id}/edit", follow_redirects=False)
    assert edit_redirect.status_code == 303
    assert f"trip_instance_id={trip_instance_id}" in edit_redirect.headers["location"]
    assert f"booking_id={booking.booking_id}" in edit_redirect.headers["location"]

    edit_page = client.get(
        f"/trip-instances/{trip_instance_id}/bookings-panel?booking_mode=edit&booking_id={booking.booking_id}",
        follow_redirects=False,
    )
    assert edit_page.status_code == 303
    edit_payload = _booking_panel_payload(client, trip_instance_id, mode="edit", booking_id=booking.booking_id)
    assert edit_payload["mode"] == "edit"
    assert edit_payload["form"] is not None

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
            "booked_price": "141.25",
            "record_locator": "EDIT01",
            "notes": "Changed airport",
        },
        follow_redirects=False,
    )
    assert edited.status_code == 303
    assert "panel=bookings" in edited.headers["location"]
    assert f"trip_instance_id={trip_instance_id}" in edited.headers["location"]

    updated_booking = next(item for item in repository.load_bookings() if item.booking_id == booking.booking_id)
    assert updated_booking.trip_instance_id == trip_instance_id
    assert updated_booking.route_option_id == ""
    assert updated_booking.booked_price == Decimal("141.25")

    detail = _booking_panel_payload(client, trip_instance_id)
    warning_rows = [row for row in detail["rows"] if row["warning"]]
    assert warning_rows
    assert any("does not match any tracked route on this date yet" in row["warning"] for row in warning_rows)
    assert any(row["offer"]["priceLabel"] == "$141.25" for row in detail["rows"])


def test_trip_detail_booking_actions_do_not_expose_cancel_or_restore(tmp_path: Path) -> None:
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

    snapshot_page = _booking_panel_payload(client, trip_instance_id)
    assert any(row["offer"]["metaLabel"].endswith("CANCEL1") for row in snapshot_page["rows"])


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

    detail = _booking_panel_payload(client, trip_instance_id)
    assert detail["rows"] == []


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
    trip_id = _trip_by_label(repository, "Warning Trip").trip_id
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


def test_group_delete_removes_rule_targets_and_preserves_trips(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    group = save_trip_group(repository, trip_group_id=None, label="Delete Protected Group")

    create = client.post(
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
    assert create.status_code == 303
    rule = _trip_by_label(repository, "Protected Rule")
    sync_and_persist(repository, today=date(2026, 4, 1))
    assert any(item.trip_group_id == group.trip_group_id for item in repository.load_rule_group_targets())
    assert any(item.trip_group_id == group.trip_group_id for item in repository.load_trip_instance_group_memberships())

    delete = client.post(
        f"/groups/{group.trip_group_id}/delete",
        headers={"referer": f"http://testserver/groups/{group.trip_group_id}"},
        follow_redirects=False,
    )
    assert delete.status_code == 303
    assert delete.headers["location"] == "/?message=Collection+deleted#dashboard-groups"
    assert all(item.trip_group_id != group.trip_group_id for item in repository.load_trip_groups())
    assert all(item.trip_group_id != group.trip_group_id for item in repository.load_rule_group_targets())
    assert all(item.trip_group_id != group.trip_group_id for item in repository.load_trip_instance_group_memberships())
    assert any(item.trip_id == rule.trip_id for item in repository.load_trips())


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
    assert delete.headers["location"] == "/?message=Collection+deleted#dashboard-groups"
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
    repository = Repository(settings)
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id

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

    detail = _booking_panel_payload(client, trip_instance_id)
    meta_labels = [row["offer"]["metaLabel"] for row in detail["rows"]]
    assert any(label.endswith("MULTI1") for label in meta_labels)
    assert any(label.endswith("MULTI2") for label in meta_labels)
    assert len(detail["rows"]) == 2


def test_trip_instance_detail_renders_live_tracker_price(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)

    response = client.post(
        "/trips",
        data={
            "label": "Priced Tracker Trip",
            "trip_kind": "one_time",
            "anchor_date": "2026-04-06",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id

    target = repository.load_tracker_fetch_targets()[0]
    target.latest_price = 185
    target.latest_departure_label = "6:00 AM"
    target.latest_fetched_at = utcnow()
    repository.upsert_tracker_fetch_targets([target])

    detail = _tracker_panel_payload(client, trip_instance_id)
    assert detail["trip"]["tripInstanceId"] == trip_instance_id
    assert any(row["offer"]["priceLabel"] == "$185" for row in detail["rows"])


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
    trip_id = _trip_by_label(Repository(settings), "Test Weekly Trip").trip_id

    pause = client.post(f"/trips/{trip_id}/pause", follow_redirects=False)
    assert pause.status_code == 303
    assert pause.headers["location"] == "/?message=Trip+paused#all-travel"

    activate = client.post(f"/trips/{trip_id}/activate", follow_redirects=False)
    assert activate.status_code == 303
    assert (
        activate.headers["location"]
        == "/?message=Trip+activated#all-travel"
    )

    pause_from_page = client.post(
        f"/trips/{trip_id}/pause",
        headers={"referer": "http://testserver/trips"},
        follow_redirects=False,
    )
    assert pause_from_page.status_code == 303
    assert pause_from_page.headers["location"] == "/?message=Trip+paused#all-travel"

    activate_from_page = client.post(
        f"/trips/{trip_id}/activate",
        headers={"referer": "http://testserver/trips"},
        follow_redirects=False,
    )
    assert activate_from_page.status_code == 303
    assert (
        activate_from_page.headers["location"]
        == "/?message=Trip+activated#all-travel"
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
    trip_id = _trip_by_label(Repository(settings), "Activation Queue Trip").trip_id

    repository = Repository(settings)
    fetch_targets = repository.load_tracker_fetch_targets()
    delayed_until = utcnow() + timedelta(hours=6)
    for target in fetch_targets:
        target.refresh_requested_at = None
        target.last_fetch_finished_at = delayed_until
    repository.replace_tracker_fetch_targets(fetch_targets)

    pause = client.post(f"/trips/{trip_id}/pause", follow_redirects=False)
    assert pause.status_code == 303

    activate = client.post(f"/trips/{trip_id}/activate", follow_redirects=False)
    assert activate.status_code == 303
    assert activate.headers["location"] == "/?message=Trip+activated#all-travel"

    refreshed_targets = repository.load_tracker_fetch_targets()
    assert len(refreshed_targets) == 16
    assert all(target.refresh_requested_at is not None for target in refreshed_targets)


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
    payload = _dashboard_payload(client)
    assert any(item["label"] == "No collection" for item in payload["filters"]["groupOptions"])
    assert any(item["label"] == "Weekly LA to SF" for collection in payload["collections"] for item in collection["recurringTrips"])
    assert any(item["trip"]["title"] == "Conference Arrival" for item in payload["trips"])


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
    payload = _dashboard_payload(client)
    trip_instance_id = payload["trips"][0]["trip"]["tripInstanceId"]

    delete_response = client.post(
        f"/trip-instances/{trip_instance_id}/delete-generated",
        headers={"referer": "http://testserver/trips"},
        follow_redirects=False,
    )
    assert delete_response.status_code == 303
    group_id = Repository(settings).load_trip_groups()[0].trip_group_id
    assert delete_response.headers["location"] == f"/?message=Trip+deleted#group-{group_id}"

    payload = _dashboard_payload(client)
    assert not any(item["trip"]["tripInstanceId"] == trip_instance_id for item in payload["trips"])


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
    trip_id = _trip_by_label(repository, "Weekly Commute").trip_id
    trip = next(item for item in repository.load_trips() if item.trip_id == trip_id)
    assert any(
        target.rule_trip_id == trip.trip_id and target.trip_group_id == group.trip_group_id
        for target in repository.load_rule_group_targets()
    )
    payload = _dashboard_payload(client, trip_group_id=group.trip_group_id)
    trip_instance_id = payload["trips"][0]["trip"]["tripInstanceId"]

    delete_response = client.post(
        f"/trip-instances/{trip_instance_id}/delete-generated",
        headers={"referer": f"http://testserver/trips?trip_group_id={group.trip_group_id}"},
        follow_redirects=False,
    )
    assert delete_response.status_code == 303
    assert delete_response.headers["location"] == f"/?message=Trip+deleted#group-{group.trip_group_id}"

    payload = _dashboard_payload(client, trip_group_id=group.trip_group_id)
    assert any(collection["groupId"] == group.trip_group_id for collection in payload["collections"])
    assert not any(item["trip"]["tripInstanceId"] == trip_instance_id for item in payload["trips"])


def test_weekly_trip_detail_redirects_to_edit_page(tmp_path: Path) -> None:
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
    trip_id = _trip_by_label(Repository(settings), "Redirect Weekly Trip").trip_id

    response = client.get(f"/trips/{trip_id}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/trips/{trip_id}/edit"


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
    repository = Repository(settings)
    trip = _trip_by_label(repository, "Redirect One-Time Trip")
    trip_instance_id = _trip_instance_id_for_trip(repository, trip.trip_id)

    response = client.get(f"/trips/{trip.trip_id}", follow_redirects=False)
    assert response.status_code == 303
    snapshot = sync_and_persist(repository)
    assert response.headers["location"] == trip_focus_url(
        snapshot,
        trip.trip_id,
        trip_instance_id=trip_instance_id,
    )


def test_weekly_trip_edit_page_warns_about_linked_trips_and_locks_trip_type(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    group = save_trip_group(repository, trip_group_id=None, label="Commute")

    create = client.post(
        "/trips",
        data={
            "label": "Protected Weekly Trip",
            "trip_kind": "weekly",
            "trip_group_ids_json": json.dumps([group.trip_group_id]),
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )

    assert create.status_code == 303
    trip_id = _trip_by_label(repository, "Protected Weekly Trip").trip_id

    edit_page = client.get(f"/trips/{trip_id}/edit")
    assert edit_page.status_code == 200
    assert '<div id="root"></div>' in edit_page.text
    form_payload = client.get(f"/api/trips/{trip_id}/edit-form")
    assert form_payload.status_code == 200
    payload = form_payload.json()
    assert payload["recurringEditWarning"]["linkedTripCount"] >= 1
    assert payload["values"]["tripKind"] == "weekly"
    assert payload["values"]["label"] == "Protected Weekly Trip"


def test_trip_instance_detail_links_attached_generated_trip_to_recurring_edit(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    group = save_trip_group(repository, trip_group_id=None, label="Commute")

    create = client.post(
        "/trips",
        data={
            "label": "Managed Weekly Trip",
            "trip_kind": "weekly",
            "trip_group_ids_json": json.dumps([group.trip_group_id]),
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id
    trip_id = repository.load_trips()[0].trip_id
    payload = _dashboard_payload(client, trip_group_id=group.trip_group_id)
    row = next(item for item in payload["trips"] if item["trip"]["tripInstanceId"] == trip_instance_id)
    assert row["trip"]["editHref"] == f"/trips/{trip_id}/edit?trip_instance_id={trip_instance_id}"


def test_group_detail_surfaces_rule_edit_button_without_rule_detail_link(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    group = save_trip_group(repository, trip_group_id=None, label="Commute")

    create = client.post(
        "/trips",
        data={
            "label": "Rule On Group",
            "trip_kind": "weekly",
            "trip_group_ids_json": json.dumps([group.trip_group_id]),
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303
    trip_id = _trip_by_label(repository, "Rule On Group").trip_id

    payload = _dashboard_payload(client)
    collection = next(item for item in payload["collections"] if item["groupId"] == group.trip_group_id)
    assert any(item["editHref"] == f"/trips/{trip_id}/edit" for item in collection["recurringTrips"])


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
            "anchor_date": (date.today() + timedelta(days=3)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    payload = _dashboard_payload(client)
    row = next(item for item in payload["trips"] if item["trip"]["title"] == "Modal Delete Trip")
    assert row["trip"]["delete"]["confirmation"]["title"] == "Delete this one-time trip?"
    assert row["trip"]["delete"]["confirmation"]["action"] == "Delete trip"


def test_one_time_trip_with_booking_can_still_be_deleted(tmp_path: Path) -> None:
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
            "label": "Delete Booked Trip",
            "trip_kind": "one_time",
            "anchor_date": (date.today() + timedelta(days=3)).isoformat(),
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
            "departure_date": (date.today() + timedelta(days=3)).isoformat(),
            "departure_time": "07:10",
            "arrival_time": "08:35",
            "booked_price": "119",
            "record_locator": "DELBOOK1",
            "notes": "",
        },
        follow_redirects=False,
    )

    payload = _dashboard_payload(client)
    row = next(item for item in payload["trips"] if item["trip"]["title"] == "Delete Booked Trip")
    assert row["trip"]["delete"]["confirmation"]["title"] == "Delete this one-time trip?"

    parent_trip_id = repository.load_trip_instances()[0].trip_id
    delete = client.post(
        f"/trips/{parent_trip_id}/delete",
        headers={"referer": "http://testserver/"},
        follow_redirects=False,
    )
    assert delete.status_code == 303
    assert "Trip+deleted.+1+booking+needs+linking." in delete.headers["location"]

    payload = _dashboard_payload(client)
    unmatched_item = next(item for item in payload["actionItems"] if item["kind"] == "unmatchedBooking")
    assert unmatched_item["offer"]["metaLabel"].endswith("DELBOOK1")


def test_generated_trip_with_booking_can_be_deleted_and_needs_relink(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    group = save_trip_group(repository, trip_group_id=None, label="Delete booked rule")

    create = client.post(
        "/trips",
        data={
            "label": "Delete Generated With Booking",
            "trip_kind": "weekly",
            "trip_group_ids_json": json.dumps([group.trip_group_id]),
            "anchor_date": "",
            "anchor_weekday": "Monday",
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
            "record_locator": "DELGEN1",
            "notes": "",
        },
        follow_redirects=False,
    )

    payload = _dashboard_payload(client)
    assert any(item["trip"]["delete"]["confirmation"]["action"] == "Delete trip" for item in payload["trips"])

    delete = client.post(
        f"/trip-instances/{trip_instance_id}/delete-generated",
        headers={"referer": "http://testserver/"},
        follow_redirects=False,
    )
    assert delete.status_code == 303
    assert "Trip+deleted.+1+booking+needs+linking." in delete.headers["location"]

    payload = _dashboard_payload(client)
    unmatched_item = next(item for item in payload["actionItems"] if item["kind"] == "unmatchedBooking")
    assert unmatched_item["offer"]["metaLabel"].endswith("DELGEN1")


def test_booking_edit_page_does_not_show_delete_controls(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    trip = save_trip(
        repository,
        trip_id=None,
        label="Edit Booking Surface",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 13),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "Southwest",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )
    sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance_id = next(
        item.trip_instance_id for item in repository.load_trip_instances() if item.trip_id == trip.trip_id
    )
    create_booking = client.post(
        "/bookings",
        data={
            "trip_instance_id": trip_instance_id,
            "airline": "Southwest",
            "origin_airport": "LAX",
            "destination_airport": "SFO",
            "departure_date": "2026-04-13",
            "departure_time": "06:00",
            "arrival_time": "07:30",
            "booked_price": "78.40",
            "record_locator": "NODELETE",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert create_booking.status_code == 303
    booking_id = repository.load_bookings()[0].booking_id

    response = client.get(
        f"/trip-instances/{trip_instance_id}/bookings-panel?booking_mode=edit&booking_id={booking_id}",
        follow_redirects=False,
    )

    assert response.status_code == 303
    edit_payload = _booking_panel_payload(client, trip_instance_id, mode="edit", booking_id=booking_id)
    assert edit_payload["mode"] == "edit"
    assert edit_payload["form"] is not None


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

    weekly_one_id = _trip_by_label(repository, "Weekly Commute A").trip_id
    weekly_one_trip = next(item for item in repository.load_trips() if item.trip_id == weekly_one_id)
    assert any(
        target.rule_trip_id == weekly_one_trip.trip_id and target.trip_group_id == work_group.trip_group_id
        for target in repository.load_rule_group_targets()
    )

    payload = _dashboard_payload(client, trip_group_id=work_group.trip_group_id)
    titles = [item["trip"]["title"] for item in payload["trips"]]
    assert payload["filters"]["selectedTripGroupIds"] == [work_group.trip_group_id]
    assert "One-off Flight" not in titles
    assert "Work Travel" in titles
    assert "Weekly Commute B" not in titles


def test_scheduled_trips_can_be_filtered_to_no_collection(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    client = TestClient(create_app(settings))
    repository = Repository(settings)
    work_group = save_trip_group(repository, trip_group_id=None, label="Work Travel")

    grouped = client.post(
        "/trips",
        data={
            "label": "Grouped Commute",
            "trip_kind": "weekly",
            "trip_group_ids_json": json.dumps([work_group.trip_group_id]),
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    ungrouped = client.post(
        "/trips",
        data={
            "label": "Ungrouped One-off",
            "trip_kind": "one_time",
            "anchor_date": "2026-05-10",
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["SFO"],"destination_airports":["JFK"],"airlines":["United"],"day_offset":0,"start_time":"08:00","end_time":"12:00"}]',
        },
        follow_redirects=False,
    )
    assert grouped.status_code == 303
    assert ungrouped.status_code == 303

    payload = _dashboard_payload(client)
    option_values = {item["value"] for item in payload["filters"]["groupOptions"]}
    assert "__ungrouped__" in option_values

    filtered_payload = _dashboard_payload(client, trip_group_id="__ungrouped__")
    filtered_titles = [item["trip"]["title"] for item in filtered_payload["trips"]]
    assert "Ungrouped One-off" in filtered_titles
    assert "Grouped Commute" not in filtered_titles


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
    trip_id = _trip_by_label(repository, "Weekly Commute A").trip_id

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

    payload = _dashboard_payload(client)
    assert any(item["label"] == "Weekly Commute A" for collection in payload["collections"] for item in collection["recurringTrips"])


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

    root_page = client.get("/")
    assert root_page.status_code == 200
    assert '<div id="root"></div>' in root_page.text


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

    payload = _dashboard_payload(client)
    titles = [item["trip"]["title"] for item in payload["trips"]]
    assert "Past Commute" not in titles
    assert titles == ["Future Commute"]


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

    trip_instance_id = _trip_instance_id_for_label(Repository(settings), "Tracker metadata")
    trackers_redirect = client.get(f"/trip-instances/{trip_instance_id}/trackers", follow_redirects=False)
    assert trackers_redirect.status_code == 303
    assert "panel=trackers" in trackers_redirect.headers["location"]
    trackers_page = client.get(f"/trip-instances/{trip_instance_id}/trackers-panel", follow_redirects=False)
    assert trackers_page.status_code == 303
    assert f"panel=trackers&trip_instance_id={trip_instance_id}" in trackers_page.headers["location"]
    tracker_payload = _tracker_panel_payload(client, trip_instance_id)

    assert any(row["offer"]["statusKind"] == "pending" for row in tracker_payload["rows"])
    assert any("BUR → SFO" in row["offer"]["detail"] for row in tracker_payload["rows"])
    assert any("LAX → SFO" in row["offer"]["detail"] for row in tracker_payload["rows"])
    assert any("google.com/travel/flights" in row["offer"]["href"] for row in tracker_payload["rows"] if row["offer"]["href"])
    assert tracker_payload["lastRefreshLabel"] == ""


def test_trip_trackers_page_shows_due_now_for_past_due_refresh(tmp_path: Path) -> None:
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
            "label": "Past due refresh",
            "trip_kind": "one_time",
            "anchor_date": (date.today() + timedelta(days=7)).isoformat(),
            "anchor_weekday": "",
            "route_options_json": '[{"origin_airports":["BUR"],"destination_airports":["SFO"],"airlines":["Alaska"],"day_offset":0,"start_time":"06:00","end_time":"10:00"}]',
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    fetch_targets = repository.load_tracker_fetch_targets()
    assert fetch_targets
    target = fetch_targets[0]
    target.last_fetch_finished_at = utcnow() - timedelta(minutes=5)
    repository.upsert_tracker_fetch_targets([target])

    trip_instance_id = _trip_instance_id_for_label(repository, "Past due refresh")
    tracker_payload = _tracker_panel_payload(client, trip_instance_id)
    assert any(row["offer"]["statusKind"] == "pending" for row in tracker_payload["rows"])
    assert "Last refresh" in tracker_payload["lastRefreshLabel"]


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

    trip_instance_id = _trip_instance_id_for_label(Repository(settings), "Refresh queue test")
    queue = client.post(f"/trip-instances/{trip_instance_id}/trackers/queue-refresh", follow_redirects=False)
    assert queue.status_code == 303
    assert "message=Refresh+requested." in queue.headers["location"]


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
    fetch_targets[0].latest_price = None
    repository.replace_tracker_fetch_targets(fetch_targets)

    trip_instance_id = _trip_instance_id_for_label(repository, "No results tracker")
    tracker_payload = _tracker_panel_payload(client, trip_instance_id)
    assert any(row["offer"]["priceLabel"] == "N/A" for row in tracker_payload["rows"])
    assert any(row["offer"]["metaLabel"] == "6:00 AM \u2013 10:00 AM" for row in tracker_payload["rows"])
    assert any("google.com/travel/flights/search" in row["offer"]["href"] for row in tracker_payload["rows"] if row["offer"]["href"])


def test_trip_trackers_page_hides_stale_target_prices(tmp_path: Path) -> None:
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
            "label": "Stale tracker price",
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
    fetch_targets[0].latest_price = 123
    fetch_targets[0].latest_fetched_at = utcnow() - timedelta(hours=80)
    fetch_targets[0].last_fetch_status = FetchTargetStatus.SUCCESS
    fetch_targets[0].last_fetch_finished_at = fetch_targets[0].latest_fetched_at
    repository.replace_tracker_fetch_targets(fetch_targets)

    trip_instance_id = _trip_instance_id_for_label(repository, "Stale tracker price")
    tracker_payload = _tracker_panel_payload(client, trip_instance_id)
    assert all(row["offer"]["priceLabel"] != "$123" for row in tracker_payload["rows"])
    assert any(row["offer"]["statusKind"] == "pending" for row in tracker_payload["rows"])


def test_unmatched_booking_can_be_linked_from_dashboard_flow(tmp_path: Path) -> None:
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

    payload = _dashboard_payload(client)
    unmatched_id = next(item["unmatchedBookingId"] for item in payload["actionItems"] if item["kind"] == "unmatchedBooking")

    repository = Repository(settings)
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id
    resolve_response = client.post(
        f"/bookings/unmatched/{unmatched_id}/link",
        data={"trip_instance_id": trip_instance_id},
        follow_redirects=False,
    )
    assert resolve_response.status_code == 303
    assert "panel=bookings" in resolve_response.headers["location"]
    assert f"trip_instance_id={trip_instance_id}" in resolve_response.headers["location"]


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

    payload = _dashboard_payload(client)
    unmatched = next(item for item in payload["actionItems"] if item["kind"] == "unmatchedBooking")
    group_labels = [group["label"] for group in unmatched["tripOptions"]]
    assert "Past trips" in group_labels
    assert "Upcoming trips" in group_labels


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

    payload = _dashboard_payload(client)
    assert payload["trips"] == []


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
    detail = _booking_panel_payload(client, trip_instance_id)
    warning_rows = [row for row in detail["rows"] if row["warning"]]

    assert warning_rows
    assert any("does not match any tracked route on this date yet" in row["warning"] for row in warning_rows)
