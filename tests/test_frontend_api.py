from __future__ import annotations

from datetime import date
from app.models.base import utcnow

from app.models.base import AppState, DataScope
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
            booked_price="78.40",
            record_locator="BDJ594",
        ),
        trip_instance_id=trip_instance_id,
    )
    sync_and_persist(repository, today=date(2026, 4, 1))
    return trip_instance_id


def _seed_grouped_recurring_trip(repository: Repository) -> str:
    group = save_trip_group(repository, trip_group_id=None, label="Commute")
    save_trip(
        repository,
        trip_id=None,
        label="Commute",
        trip_kind="weekly",
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
    trip_instance_id = next(
        instance.trip_instance_id
        for instance in repository.load_trip_instances()
        if instance.anchor_date == date(2026, 4, 20)
    )
    record_booking(
        repository,
        BookingCandidate(
            airline="Southwest",
            origin_airport="LAX",
            destination_airport="SFO",
            departure_date=date(2026, 4, 20),
            departure_time="06:00",
            arrival_time="07:20",
            booked_price="78.40",
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


def test_trip_status_mutation_dashboard_payload_hides_test_scoped_rows(client, repository: Repository) -> None:
    repository.save_app_state(AppState(show_test_data=False, process_test_data=False))
    live_trip = save_trip(
        repository,
        trip_id=None,
        label="Live recurring",
        trip_kind="weekly",
        active=True,
        anchor_date=date(2026, 4, 20),
        anchor_weekday="Monday",
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
    save_trip(
        repository,
        trip_id=None,
        label="QA Hidden recurring",
        trip_kind="weekly",
        active=True,
        anchor_date=date(2026, 4, 20),
        anchor_weekday="Wednesday",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "08:00",
                "fare_class_policy": "include_basic",
                "savings_needed_vs_previous": 0,
            }
        ],
        data_scope=DataScope.TEST,
    )
    sync_and_persist(repository, today=date(2026, 4, 1))

    response = client.patch(f"/api/trips/{live_trip.trip_id}/status", json={"active": False})

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"tripId": live_trip.trip_id, "active": False}


def test_delete_collection_api_detaches_trips_without_deleting_them(client, repository: Repository) -> None:
    group = save_trip_group(repository, trip_group_id=None, label="Commute")
    recurring_trip = save_trip(
        repository,
        trip_id=None,
        label="Recurring commute",
        trip_kind="weekly",
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
    one_time_trip = save_trip(
        repository,
        trip_id=None,
        label="One-off commute",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 20),
        anchor_weekday="Monday",
        trip_group_ids=[group.trip_group_id],
        route_option_payloads=[
            {
                "origin_airports": "SFO",
                "destination_airports": "BUR",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "18:00",
                "end_time": "21:00",
                "fare_class_policy": "include_basic",
                "savings_needed_vs_previous": 0,
            }
        ],
        data_scope=DataScope.LIVE,
    )
    sync_and_persist(repository, today=date(2026, 4, 1))

    assert any(item.trip_group_id == group.trip_group_id for item in repository.load_trip_groups())
    assert any(item.trip_group_id == group.trip_group_id for item in repository.load_rule_group_targets())
    assert any(item.trip_group_id == group.trip_group_id for item in repository.load_trip_instance_group_memberships())

    response = client.delete(f"/api/collections/{group.trip_group_id}")

    assert response.status_code == 204
    assert all(item.trip_group_id != group.trip_group_id for item in repository.load_trip_groups())
    assert all(item.trip_group_id != group.trip_group_id for item in repository.load_rule_group_targets())
    assert all(item.trip_group_id != group.trip_group_id for item in repository.load_trip_instance_group_memberships())
    assert any(item.trip_id == recurring_trip.trip_id for item in repository.load_trips())
    assert any(item.trip_id == one_time_trip.trip_id for item in repository.load_trips())


def test_update_trip_editor_redirect_does_not_select_collection_filter(client, repository: Repository) -> None:
    group = save_trip_group(repository, trip_group_id=None, label="Commute")
    trip = save_trip(
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
    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance_id = next(
        item.trip_instance_id for item in snapshot.trip_instances if item.trip_id == trip.trip_id and not item.deleted
    )

    form_response = client.get(f"/api/trips/{trip.trip_id}/edit-form")
    assert form_response.status_code == 200
    payload = form_response.json()

    save_response = client.patch(
        f"/api/trips/{trip.trip_id}/editor",
        json={
            **payload["values"],
            "label": "Commute updated",
            "routeOptions": payload["routeOptions"],
        },
    )

    assert save_response.status_code == 200
    assert save_response.json()["redirectTo"] == f"/#scheduled-{trip_instance_id}"


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


def test_unmatched_booking_form_and_update_api(client, repository: Repository) -> None:
    _seed_dashboard_trip(repository)
    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Alaska",
            origin_airport="JFK",
            destination_airport="LAX",
            departure_date=date(2026, 6, 10),
            departure_time="21:30",
            arrival_time="00:45",
            booked_price="36.20",
            record_locator="SKLOAK",
        ),
    )
    assert booking is None
    assert unmatched is not None
    sync_and_persist(repository, today=date(2026, 4, 1))

    form_response = client.get(f"/api/unmatched-bookings/{unmatched.unmatched_booking_id}/form")

    assert form_response.status_code == 200
    form_payload = form_response.json()
    assert form_payload["dateTile"] == {"weekday": "WED", "monthDay": "Jun 10"}
    assert form_payload["form"]["values"]["recordLocator"] == "SKLOAK"
    assert form_payload["form"]["values"]["tripInstanceId"] == ""

    update_response = client.patch(
        f"/api/unmatched-bookings/{unmatched.unmatched_booking_id}",
        json={
            "tripInstanceId": "",
            "airline": "Delta",
            "originAirport": "JFK",
            "destinationAirport": "LAX",
            "departureDate": "2026-06-10",
            "departureTime": "21:45",
            "arrivalTime": "01:00",
            "bookedPrice": "41.20",
            "recordLocator": "EDIT01",
            "notes": "Updated from modal",
        },
    )

    assert update_response.status_code == 200
    assert update_response.json() == {"ok": True}
    dashboard = client.get("/api/dashboard").json()
    unmatched_item = next(item for item in dashboard["actionItems"] if item["kind"] == "unmatchedBooking")
    assert unmatched_item["offer"]["detail"] == "JFK → LAX · Delta"
    assert unmatched_item["offer"]["metaLabel"].endswith("EDIT01")


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
    rebook_items = [
        item for item in payload["actionItems"] if item.get("attentionKind") in {"priceDrop", "betterOption"}
    ]
    assert rebook_items == []


def test_dashboard_api_uses_price_drop_copy_for_same_route_rebook(client, repository: Repository) -> None:
    trip_instance_id = _seed_dashboard_trip(repository)

    trackers = repository.load_trackers()
    now = utcnow()
    for tracker in trackers:
        tracker.latest_observed_price = 70
        tracker.latest_fetched_at = now
        tracker.last_signal_at = now
        tracker.latest_signal_source = "background_fetch"
    repository.upsert_trackers(trackers)

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    rebook_items = [item for item in payload["actionItems"] if item.get("attentionKind") == "priceDrop"]
    assert len(rebook_items) == 1
    assert rebook_items[0]["title"] == "Price drop"
    assert rebook_items[0]["badge"] == "$8.40 lower"


def test_dashboard_api_uses_better_option_copy_for_cross_route_rebook(client, repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Cross-route commute",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 20),
        anchor_weekday="Monday",
        route_option_payloads=[
            {
                "origin_airports": "SFO",
                "destination_airports": "BUR",
                "airlines": "Southwest",
                "day_offset": 0,
                "start_time": "17:00",
                "end_time": "22:00",
                "fare_class_policy": "include_basic",
                "savings_needed_vs_previous": 0,
            },
            {
                "origin_airports": "SFO",
                "destination_airports": "LAX",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "17:00",
                "end_time": "22:00",
                "fare_class_policy": "exclude_basic",
                "savings_needed_vs_previous": 30,
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
            origin_airport="SFO",
            destination_airport="LAX",
            departure_date=date(2026, 4, 20),
            departure_time="18:01",
            arrival_time="19:33",
            fare_class="economy",
            booked_price="78.40",
            record_locator="ORBKFC",
        ),
        trip_instance_id=trip_instance_id,
    )
    sync_and_persist(repository, today=date(2026, 4, 1))

    trackers = repository.load_trackers()
    now = utcnow()
    for tracker in trackers:
        if tracker.rank == 1:
            tracker.latest_observed_price = 96
        elif tracker.rank == 2:
            tracker.latest_observed_price = 130
        tracker.latest_fetched_at = now
        tracker.last_signal_at = now
        tracker.latest_signal_source = "background_fetch"
    repository.upsert_trackers(trackers)

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    rebook_items = [item for item in payload["actionItems"] if item.get("attentionKind") == "betterOption"]
    assert len(rebook_items) == 1
    assert rebook_items[0]["title"] == "Better option after preferences"
    assert rebook_items[0]["badge"] == ""


def test_dashboard_api_collection_pills_expose_lifecycle_and_attention_kind(client, repository: Repository) -> None:
    trip_instance_id = _seed_grouped_recurring_trip(repository)

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    pill = payload["collections"][0]["upcomingTrips"][0]
    assert pill["lifecycle"] == "booked"
    assert pill["attentionKind"] == ""

    trackers = repository.load_trackers()
    now = utcnow()
    for tracker in trackers:
        if tracker.trip_instance_id == trip_instance_id:
            tracker.latest_observed_price = 70
            tracker.latest_fetched_at = now
            tracker.last_signal_at = now
            tracker.latest_signal_source = "background_fetch"
    repository.upsert_trackers(trackers)

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    pill = payload["collections"][0]["upcomingTrips"][0]
    assert pill["attentionKind"] == "priceDrop"
