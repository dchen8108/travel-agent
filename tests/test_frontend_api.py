from __future__ import annotations

from datetime import date
from app.models.base import utcnow

from app.models.base import DataScope
from app.services.bookings import BookingCandidate, record_booking
from app.services.groups import save_trip_group
from app.services.trips import save_trip
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
import app.storage.repository as repository_module


def _seed_dashboard_trip(repository: Repository) -> str:
    group = save_trip_group(repository, trip_group_id=None, label="Commute")
    save_trip(
        repository,
        trip_id=None,
        label="Commute",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 20),
        anchor_weekday="Monday",
        trip_group_ids=[group.trip_group_id],
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "Southwest",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "08:00",
                "fare_class_policy": "include_basic",
                "savings_needed_vs_previous": 0,
            }
        ],
        data_scope=DataScope.LIVE,
    )
    sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id
    record_booking(
        repository,
        BookingCandidate(
            airline="Southwest",
            origin_airport="LAX",
            destination_airport="SFO",
            departure_date=date(2026, 4, 20),
            departure_time="06:00",
            arrival_time="07:20",
            booked_price=7840,
            record_locator="BDJ594",
        ),
        trip_instance_id=trip_instance_id,
    )
    sync_and_persist(repository, today=date(2026, 4, 1))
    return trip_instance_id


def test_repository_initialization_is_shared_per_db_path(settings, monkeypatch) -> None:
    calls = 0
    real_initialize = repository_module.initialize_schema

    def wrapped_initialize(connection) -> None:
        nonlocal calls
        calls += 1
        real_initialize(connection)

    monkeypatch.setattr(repository_module, "initialize_schema", wrapped_initialize)

    repository_one = Repository(settings)
    repository_one.ensure_data_dir()
    repository_two = Repository(settings)
    repository_two.ensure_data_dir()

    assert calls == 1


def test_dashboard_api_returns_collections_and_trip_rows(client, repository: Repository) -> None:
    _seed_dashboard_trip(repository)

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["collections"][0]["label"] == "Commute"
    assert payload["trips"][0]["trip"]["title"] == "Commute"
    assert payload["trips"][0]["trip"]["dateTile"]["monthDay"] == "Apr 20"
    assert payload["trips"][0]["bookedOffer"]["metaLabel"].endswith("BDJ594")


def test_trip_panel_apis_return_booking_and_tracker_payloads(client, repository: Repository) -> None:
    trip_instance_id = _seed_dashboard_trip(repository)

    bookings_response = client.get(f"/api/trip-instances/{trip_instance_id}/bookings?mode=list")
    booking_form_response = client.get(f"/api/trip-instances/{trip_instance_id}/booking-form")
    trackers_response = client.get(f"/api/trip-instances/{trip_instance_id}/trackers")
    create_response = client.get(f"/api/trip-instances/{trip_instance_id}/bookings?mode=create")

    assert bookings_response.status_code == 200
    assert bookings_response.json()["rows"][0]["offer"]["detail"] == "LAX → SFO · Southwest"
    assert bookings_response.json()["form"] is None
    assert bookings_response.json()["catalogs"] is None
    assert booking_form_response.status_code == 200
    assert booking_form_response.json()["form"]["values"]["tripInstanceId"] == trip_instance_id
    assert trackers_response.status_code == 200
    assert trackers_response.json()["trip"]["title"] == "Commute"
    assert trackers_response.json()["rows"]
    assert create_response.status_code == 200
    assert create_response.json()["form"]["values"]["tripInstanceId"] == trip_instance_id


def test_dashboard_api_suppresses_rebook_card_when_preference_buffer_erases_raw_savings(
    client,
    repository: Repository,
) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Preference commute",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 20),
        anchor_weekday="Monday",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
                "fare_class_policy": "include_basic",
                "savings_needed_vs_previous": 0,
            },
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "United",
                "day_offset": 0,
                "start_time": "18:00",
                "end_time": "22:00",
                "fare_class_policy": "include_basic",
                "savings_needed_vs_previous": 50,
            },
        ],
        preference_mode="ranked_bias",
        data_scope=DataScope.LIVE,
    )
    sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id
    record_booking(
        repository,
        BookingCandidate(
            airline="Alaska",
            origin_airport="BUR",
            destination_airport="SFO",
            departure_date=date(2026, 4, 20),
            departure_time="07:00",
            arrival_time="08:20",
            booked_price=180,
            record_locator="PREF01",
        ),
        trip_instance_id=trip_instance_id,
    )
    sync_and_persist(repository, today=date(2026, 4, 1))

    trackers = repository.load_trackers()
    now = utcnow()
    for tracker in trackers:
        if tracker.rank == 1:
            tracker.latest_observed_price = 180
        elif tracker.rank == 2:
            tracker.latest_observed_price = 130
        tracker.latest_fetched_at = now
        tracker.last_signal_at = now
        tracker.latest_signal_source = "background_fetch"
    repository.upsert_trackers(trackers)

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    rebook_items = [item for item in payload["actionItems"] if item.get("attentionKind") == "rebook"]
    assert rebook_items == []
