from __future__ import annotations

from datetime import date, timedelta
from app.models.base import utcnow

from app.models.base import AppState, DataScope
from app.services.bookings import BookingCandidate, record_booking
from app.services.google_flights_fetcher import GoogleFlightsOffer
from app.services.groups import save_trip_group
from app.services.price_records import SuccessfulFetchRecord, build_price_records
from app.services.trips import save_trip
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
import app.storage.repository as repository_module


def _next_weekday(weekday: int) -> date:
    today = date.today()
    days_ahead = (weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def _seed_dashboard_trip(repository: Repository) -> str:
    anchor_date = _next_weekday(0)
    group = save_trip_group(repository, trip_group_id=None, label="Commute")
    save_trip(
        repository,
        trip_id=None,
        label="Commute",
        trip_kind="one_time",
        active=True,
        anchor_date=anchor_date,
        anchor_weekday=anchor_date.strftime("%A"),
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
    sync_and_persist(repository, today=anchor_date - timedelta(days=14))
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id
    record_booking(
        repository,
        BookingCandidate(
            airline="Southwest",
            origin_airport="LAX",
            destination_airport="SFO",
            departure_date=anchor_date,
            departure_time="06:00",
            arrival_time="07:20",
            booked_price="78.40",
            record_locator="BDJ594",
        ),
        trip_instance_id=trip_instance_id,
    )
    sync_and_persist(repository, today=anchor_date - timedelta(days=14))
    return trip_instance_id


def _seed_grouped_recurring_trip(repository: Repository) -> str:
    anchor_date = _next_weekday(0)
    group = save_trip_group(repository, trip_group_id=None, label="Commute")
    save_trip(
        repository,
        trip_id=None,
        label="Commute",
        trip_kind="weekly",
        active=True,
        anchor_date=anchor_date,
        anchor_weekday=anchor_date.strftime("%A"),
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
    sync_and_persist(repository, today=anchor_date - timedelta(days=14))
    trip_instance_id = next(
        instance.trip_instance_id
        for instance in repository.load_trip_instances()
        if instance.anchor_date == anchor_date
    )
    record_booking(
        repository,
        BookingCandidate(
            airline="Southwest",
            origin_airport="LAX",
            destination_airport="SFO",
            departure_date=anchor_date,
            departure_time="06:00",
            arrival_time="07:20",
            booked_price="78.40",
            record_locator="BDJ594",
        ),
        trip_instance_id=trip_instance_id,
    )
    sync_and_persist(repository, today=anchor_date - timedelta(days=14))
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
    trip_instance_id = _seed_dashboard_trip(repository)

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    trip_instance = next(item for item in repository.load_trip_instances() if item.trip_instance_id == trip_instance_id)
    assert payload["collections"][0]["label"] == "Commute"
    assert payload["trips"][0]["trip"]["title"] == "Commute"
    assert payload["trips"][0]["trip"]["dateTile"]["monthDay"] == trip_instance.anchor_date.strftime("%b %d")
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
    anchor_date = _next_weekday(0)
    group = save_trip_group(repository, trip_group_id=None, label="Commute")
    trip = save_trip(
        repository,
        trip_id=None,
        label="Commute",
        trip_kind="one_time",
        active=True,
        anchor_date=anchor_date,
        anchor_weekday=anchor_date.strftime("%A"),
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
    snapshot = sync_and_persist(repository, today=anchor_date - timedelta(days=14))
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
    assert bookings_response.json()["rows"][0]["offer"]["detail"] == "LAX → SFO"
    assert bookings_response.json()["rows"][0]["offer"]["metaBadges"] == []
    assert bookings_response.json()["form"] is None
    assert bookings_response.json()["catalogs"] is None
    assert booking_form_response.status_code == 200
    assert booking_form_response.json()["form"]["values"]["tripInstanceId"] == trip_instance_id
    assert trackers_response.status_code == 200
    assert trackers_response.json()["trip"]["title"] == "Commute"
    assert trackers_response.json()["rows"] == []
    assert trackers_response.json()["emptyLabel"] == "Checking live fares…"
    assert create_response.status_code == 200
    assert create_response.json()["form"]["values"]["tripInstanceId"] == trip_instance_id


def test_dashboard_booking_actions_distinguish_zero_one_and_multiple_bookings(client, repository: Repository) -> None:
    base_date = _next_weekday(0)

    zero_trip = save_trip(
        repository,
        trip_id=None,
        label="Zero booking trip",
        trip_kind="one_time",
        active=True,
        anchor_date=base_date,
        anchor_weekday=base_date.strftime("%A"),
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
    single_date = base_date + timedelta(days=1)
    single_trip = save_trip(
        repository,
        trip_id=None,
        label="Single booking trip",
        trip_kind="one_time",
        active=True,
        anchor_date=single_date,
        anchor_weekday=single_date.strftime("%A"),
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
    multi_date = base_date + timedelta(days=2)
    multi_trip = save_trip(
        repository,
        trip_id=None,
        label="Multi booking trip",
        trip_kind="one_time",
        active=True,
        anchor_date=multi_date,
        anchor_weekday=multi_date.strftime("%A"),
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
    sync_and_persist(repository, today=base_date - timedelta(days=14))

    trip_instances = {item.trip_id: item.trip_instance_id for item in repository.load_trip_instances()}
    single_instance_id = trip_instances[single_trip.trip_id]
    multi_instance_id = trip_instances[multi_trip.trip_id]

    single_booking, _ = record_booking(
        repository,
        BookingCandidate(
            airline="Southwest",
            origin_airport="LAX",
            destination_airport="SFO",
            departure_date=single_date,
            departure_time="06:00",
            arrival_time="07:20",
            booked_price="78.40",
            record_locator="SINGLE1",
        ),
        trip_instance_id=single_instance_id,
    )
    assert single_booking is not None
    first_multi = record_booking(
        repository,
        BookingCandidate(
            airline="Southwest",
            origin_airport="LAX",
            destination_airport="SFO",
            departure_date=multi_date,
            departure_time="06:00",
            arrival_time="07:20",
            booked_price="81.00",
            record_locator="MULTI01",
        ),
        trip_instance_id=multi_instance_id,
    )
    second_multi = record_booking(
        repository,
        BookingCandidate(
            airline="Southwest",
            origin_airport="LAX",
            destination_airport="SFO",
            departure_date=multi_date,
            departure_time="06:15",
            arrival_time="07:35",
            booked_price="84.00",
            record_locator="MULTI02",
        ),
        trip_instance_id=multi_instance_id,
    )
    assert first_multi[0] is not None
    assert second_multi[0] is not None
    sync_and_persist(repository, today=base_date - timedelta(days=14))

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    rows_by_title = {row["trip"]["title"]: row for row in response.json()["trips"]}

    zero_actions = rows_by_title[zero_trip.label]["actions"]
    assert zero_actions["canCreateBooking"] is True
    assert zero_actions["showBookingModal"] is False
    assert zero_actions["editBookingId"] == ""

    single_actions = rows_by_title[single_trip.label]["actions"]
    assert single_actions["canCreateBooking"] is False
    assert single_actions["showBookingModal"] is False
    assert single_actions["editBookingId"] == single_booking.booking_id

    multi_actions = rows_by_title[multi_trip.label]["actions"]
    assert multi_actions["canCreateBooking"] is False
    assert multi_actions["showBookingModal"] is True
    assert multi_actions["editBookingId"] == ""


def test_tracker_panel_inlines_day_offset_into_fallback_window_times(client, repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Offset tracker trip",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 20),
        anchor_weekday="Monday",
        route_option_payloads=[
            {
                "origin_airports": "SFO",
                "destination_airports": "LAX",
                "airlines": "Southwest",
                "day_offset": 1,
                "start_time": "16:00",
                "end_time": "22:00",
                "fare_class_policy": "include_basic",
                "savings_needed_vs_previous": 0,
            }
        ],
        data_scope=DataScope.LIVE,
    )
    sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id
    tracker = repository.load_trackers()[0]
    target = repository.load_tracker_fetch_targets()[0]
    fetched_at = utcnow()
    target.latest_price = 109
    target.latest_airline = "Southwest"
    target.latest_departure_label = "4:00 PM on Thu, Apr 21"
    target.latest_arrival_label = "10:00 PM on Thu, Apr 21"
    target.latest_fetched_at = fetched_at
    target.last_fetch_finished_at = fetched_at
    target.last_fetch_status = "success"
    target.google_flights_url = "https://example.com/gf"
    repository.upsert_tracker_fetch_targets([target])
    tracker.latest_observed_price = 109
    tracker.latest_winning_origin_airport = "SFO"
    tracker.latest_winning_destination_airport = "LAX"
    tracker.latest_fetched_at = fetched_at
    repository.upsert_trackers([tracker])
    repository.append_price_records(build_price_records(
        trips=repository.load_trips(),
        trip_instances=repository.load_trip_instances(),
        trackers=repository.load_trackers(),
        fetch_targets=repository.load_tracker_fetch_targets(),
        successful_fetches=[
            SuccessfulFetchRecord(
                fetch_target_id=target.fetch_target_id,
                fetched_at=fetched_at,
                offers=[
                    GoogleFlightsOffer(
                        airline="Southwest",
                        departure_label="4:00 PM on Thu, Apr 21",
                        arrival_label="10:00 PM on Thu, Apr 21",
                        price=109,
                        price_text="$109",
                    ),
                ],
            )
        ],
    ))

    trackers_response = client.get(f"/api/trip-instances/{trip_instance_id}/trackers")

    assert trackers_response.status_code == 200
    assert trackers_response.json()["rows"][0]["offer"]["primaryMetaLabel"] == "4:00 PM⁺¹ → 10:00 PM⁺¹"


def test_tracker_panel_inlines_day_offset_into_fetched_times_with_explicit_date_text(client, repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Offset fetched tracker trip",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 20),
        anchor_weekday="Monday",
        route_option_payloads=[
            {
                "origin_airports": "SFO",
                "destination_airports": "LAX",
                "airlines": "Southwest",
                "day_offset": 1,
                "start_time": "16:00",
                "end_time": "22:00",
                "fare_class_policy": "include_basic",
                "savings_needed_vs_previous": 0,
            }
        ],
        data_scope=DataScope.LIVE,
    )
    sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id
    tracker = repository.load_trackers()[0]
    target = repository.load_tracker_fetch_targets()[0]
    target.latest_price = 109
    target.latest_airline = "Southwest"
    target.latest_departure_label = "8:10 PM on Thu, Apr 21"
    target.latest_arrival_label = "9:40 PM on Fri, Apr 22"
    target.google_flights_url = "https://example.com/gf"
    fetched_at = utcnow()
    target.latest_fetched_at = fetched_at
    target.last_fetch_finished_at = fetched_at
    target.last_fetch_status = "success"
    repository.upsert_tracker_fetch_targets([target])
    tracker.latest_observed_price = 109
    tracker.latest_winning_origin_airport = "SFO"
    tracker.latest_winning_destination_airport = "LAX"
    tracker.latest_fetched_at = fetched_at
    repository.upsert_trackers([tracker])
    repository.append_price_records(build_price_records(
        trips=repository.load_trips(),
        trip_instances=repository.load_trip_instances(),
        trackers=repository.load_trackers(),
        fetch_targets=repository.load_tracker_fetch_targets(),
        successful_fetches=[
            SuccessfulFetchRecord(
                fetch_target_id=target.fetch_target_id,
                fetched_at=fetched_at,
                offers=[
                    GoogleFlightsOffer(
                        airline="Southwest",
                        departure_label="8:10 PM on Thu, Apr 21",
                        arrival_label="9:40 PM on Fri, Apr 22",
                        price=109,
                        price_text="$109",
                    ),
                ],
            )
        ],
    ))

    trackers_response = client.get(f"/api/trip-instances/{trip_instance_id}/trackers")

    assert trackers_response.status_code == 200
    assert trackers_response.json()["rows"][0]["offer"]["primaryMetaLabel"] == "8:10 PM⁺¹ → 9:40 PM⁺²"


def test_tracker_panel_merges_latest_matching_flights_sorted_by_effective_price(client, repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Ranked flights",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 20),
        anchor_weekday="Monday",
        preference_mode="ranked_bias",
        route_option_payloads=[
            {
                "origin_airports": "SFO",
                "destination_airports": "BUR",
                "airlines": "Southwest",
                "day_offset": 0,
                "start_time": "17:00",
                "end_time": "20:00",
                "fare_class_policy": "include_basic",
                "savings_needed_vs_previous": 0,
            },
            {
                "origin_airports": "LAX",
                "destination_airports": "BUR",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "17:00",
                "end_time": "20:00",
                "fare_class_policy": "include_basic",
                "savings_needed_vs_previous": 50,
            },
        ],
        data_scope=DataScope.LIVE,
    )
    sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id
    trackers = repository.load_trackers()
    targets = repository.load_tracker_fetch_targets()
    targets_by_origin = {target.origin_airport: target for target in targets}
    fetched_at = utcnow()
    for tracker in trackers:
        tracker.latest_fetched_at = fetched_at
        tracker.latest_observed_price = 1
        tracker.preference_bias_dollars = 0 if tracker.origin_airports == "SFO" else 50
        repository.upsert_trackers([tracker])
    for target in targets:
        target.latest_fetched_at = fetched_at
        target.last_fetch_finished_at = fetched_at
        target.last_fetch_status = "success"
        target.latest_price = 100 if target.origin_airport == "SFO" else 60
        repository.upsert_tracker_fetch_targets([target])
    repository.append_price_records(build_price_records(
        trips=repository.load_trips(),
        trip_instances=repository.load_trip_instances(),
        trackers=repository.load_trackers(),
        fetch_targets=repository.load_tracker_fetch_targets(),
        successful_fetches=[
            SuccessfulFetchRecord(
                fetch_target_id=targets_by_origin["SFO"].fetch_target_id,
                fetched_at=fetched_at,
                offers=[
                    GoogleFlightsOffer(
                        airline="Southwest",
                        departure_label="5:15 PM",
                        arrival_label="6:40 PM",
                        price=100,
                        price_text="$100",
                    ),
                    GoogleFlightsOffer(
                        airline="Southwest",
                        departure_label="9:15 PM",
                        arrival_label="10:40 PM",
                        price=80,
                        price_text="$80",
                    ),
                ],
            ),
            SuccessfulFetchRecord(
                fetch_target_id=targets_by_origin["LAX"].fetch_target_id,
                fetched_at=fetched_at,
                offers=[
                    GoogleFlightsOffer(
                        airline="Alaska",
                        departure_label="5:55 PM",
                        arrival_label="7:28 PM",
                        price=60,
                        price_text="$60",
                    ),
                ],
            ),
        ],
    ))

    trackers_response = client.get(f"/api/trip-instances/{trip_instance_id}/trackers")

    assert trackers_response.status_code == 200
    payload = trackers_response.json()
    assert [row["offer"]["detail"] for row in payload["rows"]] == ["SFO → BUR", "LAX → BUR"]
    assert [row["offer"]["priceLabel"] for row in payload["rows"]] == ["$100", "$60"]


def test_booking_delete_and_unlink_api_mutations_return_updated_panel(client, repository: Repository) -> None:
    trip_instance_id = _seed_dashboard_trip(repository)
    extra_booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Southwest",
            origin_airport="LAX",
            destination_airport="SFO",
            departure_date=date(2026, 4, 20),
            departure_time="06:35",
            arrival_time="07:55",
            booked_price="82.00",
            record_locator="MULTI02",
        ),
        trip_instance_id=trip_instance_id,
    )
    assert extra_booking is not None
    assert unmatched is None
    sync_and_persist(repository, today=date(2026, 4, 1))

    bookings = repository.load_bookings()
    original_booking = next(item for item in bookings if item.record_locator == "BDJ594")
    extra_booking = next(item for item in bookings if item.record_locator == "MULTI02")

    unlink_response = client.post(f"/api/bookings/{extra_booking.booking_id}/unlink")

    assert unlink_response.status_code == 200
    unlink_payload = unlink_response.json()
    assert unlink_payload["panel"] is not None
    assert len(unlink_payload["panel"]["rows"]) == 1
    assert unlink_payload["panel"]["rows"][0]["bookingId"] == original_booking.booking_id

    delete_response = client.delete(f"/api/bookings/{original_booking.booking_id}")

    assert delete_response.status_code == 200
    delete_payload = delete_response.json()
    assert delete_payload["panel"] is not None
    assert delete_payload["panel"]["rows"] == []


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
            arrival_day_offset=1,
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
    assert form_payload["form"]["values"]["arrivalDayOffset"] == "1"

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
            "arrivalDayOffset": 1,
            "bookedPrice": "41.20",
            "recordLocator": "EDIT01",
            "notes": "Updated from modal",
        },
    )

    assert update_response.status_code == 200
    assert update_response.json() == {"ok": True}
    dashboard = client.get("/api/dashboard").json()
    unmatched_item = next(item for item in dashboard["actionItems"] if item["kind"] == "unmatchedBooking")
    assert unmatched_item["offer"]["detail"] == "JFK → LAX"
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
    assert "badge" not in rebook_items[0]


def test_dashboard_api_uses_better_option_copy_for_cross_route_rebook(client, repository: Repository) -> None:
    anchor_date = _next_weekday(0)
    save_trip(
        repository,
        trip_id=None,
        label="Cross-route commute",
        trip_kind="one_time",
        active=True,
        anchor_date=anchor_date,
        anchor_weekday=anchor_date.strftime("%A"),
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
    sync_and_persist(repository, today=anchor_date - timedelta(days=14))
    trip_instance_id = repository.load_trip_instances()[0].trip_instance_id
    record_booking(
        repository,
        BookingCandidate(
            airline="Alaska",
            origin_airport="SFO",
            destination_airport="LAX",
            departure_date=anchor_date,
            departure_time="18:01",
            arrival_time="19:33",
            fare_class="economy",
            booked_price="78.40",
            record_locator="ORBKFC",
        ),
        trip_instance_id=trip_instance_id,
    )
    sync_and_persist(repository, today=anchor_date - timedelta(days=14))

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
    assert "badge" not in rebook_items[0]


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
