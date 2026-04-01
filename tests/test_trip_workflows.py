from __future__ import annotations

from datetime import date

from app.services.google_flights import build_google_flights_query_url, normalize_google_flights_url
from app.services.dashboard import horizon_instances_for_trip, past_instances_for_trip
from app.services.trips import save_past_trip, save_trip, set_trip_active
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


def test_weekly_trip_generates_twelve_future_instances(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="LA to SF Outbound",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX",
                "destination_airports": "SFO",
                "airlines": "Alaska|United",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 3, 31))
    trip_instances = [item for item in snapshot.trip_instances if item.trip_id == trip.trip_id]

    assert len(trip_instances) == 12
    assert trip_instances[0].anchor_date == date(2026, 4, 6)
    assert all(instance.display_label.startswith("LA to SF Outbound") for instance in trip_instances)
    assert all(instance.instance_kind == "generated" for instance in trip_instances)
    assert len([tracker for tracker in snapshot.trackers if tracker.trip_instance_id == trip_instances[0].trip_instance_id]) == 1


def test_skipped_occurrence_survives_reconciliation(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="SF to LA Return",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Wednesday",
        route_option_payloads=[
            {
                "origin_airports": "SFO",
                "destination_airports": "BUR|LAX",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "17:00",
                "end_time": "22:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 3, 31))
    trip_instance = next(item for item in snapshot.trip_instances if item.trip_id == trip.trip_id)
    trip_instance.travel_state = "skipped"
    repository.save_trip_instances(snapshot.trip_instances)

    refreshed = sync_and_persist(repository, today=date(2026, 4, 2))
    same_instance = next(item for item in refreshed.trip_instances if item.trip_instance_id == trip_instance.trip_instance_id)
    assert same_instance.travel_state == "skipped"


def test_deactivating_weekly_trip_preserves_existing_instances_without_growing_frontier(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="LA to SF Weekly",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX",
                "destination_airports": "SFO",
                "airlines": "Alaska|United",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    initial = sync_and_persist(repository, today=date(2026, 3, 31))
    initial_instances = [item for item in initial.trip_instances if item.trip_id == trip.trip_id]
    initial_dates = [item.anchor_date for item in initial_instances]
    initial_tracker_ids = {
        tracker.tracker_id
        for tracker in initial.trackers
        if any(instance.trip_instance_id == tracker.trip_instance_id for instance in initial_instances)
    }
    assert len(initial_dates) == 12

    set_trip_active(repository, trip.trip_id, False)
    paused = sync_and_persist(repository, today=date(2026, 4, 21))
    paused_instances = [item for item in paused.trip_instances if item.trip_id == trip.trip_id]
    paused_dates = [item.anchor_date for item in paused_instances]
    paused_tracker_ids = {
        tracker.tracker_id
        for tracker in paused.trackers
        if any(instance.trip_instance_id == tracker.trip_instance_id for instance in paused_instances)
    }

    assert paused_dates == initial_dates
    assert paused_tracker_ids == initial_tracker_ids
    assert all(instance.instance_kind == "generated" for instance in paused_instances)


def test_trip_labels_must_be_unique(repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Conference Arrival",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SEA",
                "airlines": "Delta",
                "day_offset": 0,
                "start_time": "07:00",
                "end_time": "11:00",
            }
        ],
    )

    try:
        save_trip(
            repository,
            trip_id=None,
            label="Conference Arrival",
            trip_kind="one_time",
            active=True,
            anchor_date=date(2026, 5, 12),
            anchor_weekday="",
            route_option_payloads=[
                {
                    "origin_airports": "SEA",
                    "destination_airports": "LAX",
                    "airlines": "Delta",
                    "day_offset": 0,
                    "start_time": "12:00",
                    "end_time": "16:00",
                }
            ],
        )
    except ValueError as exc:
        assert "unique" in str(exc).lower()
    else:
        raise AssertionError("Expected duplicate trip labels to raise.")


def test_one_time_trip_creates_a_standalone_instance(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Conference Arrival",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SEA",
                "airlines": "Delta",
                "day_offset": 0,
                "start_time": "07:00",
                "end_time": "11:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instances = [item for item in snapshot.trip_instances if item.trip_id == trip.trip_id]

    assert len(trip_instances) == 1
    assert trip_instances[0].display_label == "Conference Arrival"
    assert trip_instances[0].instance_kind == "standalone"


def test_recurring_trip_keeps_past_instances_but_horizon_only_shows_future(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Weekly Commute History",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
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

    sync_and_persist(repository, today=date(2026, 3, 24))
    snapshot = sync_and_persist(repository, today=date(2026, 3, 31))

    trip_instances = [item for item in snapshot.trip_instances if item.trip_id == trip.trip_id]
    assert len(trip_instances) == 13
    assert len(horizon_instances_for_trip(snapshot, trip.trip_id, today=date(2026, 3, 31))) == 12
    assert len(past_instances_for_trip(snapshot, trip.trip_id, today=date(2026, 3, 31))) == 1


def test_save_past_trip_creates_historical_instance_without_trackers(repository: Repository) -> None:
    trip = save_past_trip(
        repository,
        trip_id=None,
        label="Old conference hop",
        anchor_date=date(2026, 3, 10),
    )

    snapshot = sync_and_persist(repository, today=date(2026, 3, 31))
    trip_instances = [item for item in snapshot.trip_instances if item.trip_id == trip.trip_id]
    trackers = [item for item in snapshot.trackers if item.trip_instance_id in {instance.trip_instance_id for instance in trip_instances}]

    assert len(trip_instances) == 1
    assert trip_instances[0].display_label == "Old conference hop"
    assert trip_instances[0].instance_kind == "standalone"
    assert trip_instances[0].anchor_date == date(2026, 3, 10)
    assert trip_instances[0].recommendation_state == "wait"
    assert len(trackers) == 0


def test_generated_google_flights_url_uses_structured_tfs_query(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Seed search test",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX",
                "destination_airports": "SFO|OAK",
                "airlines": "Alaska|United",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance = next(item for item in snapshot.trip_instances if item.trip_id == trip.trip_id)
    tracker = next(item for item in snapshot.trackers if item.trip_instance_id == trip_instance.trip_instance_id)

    url = build_google_flights_query_url(tracker)

    assert url == "https://www.google.com/travel/flights/search?tfs=GiQSCjIwMjYtMDUtMTAoADICQVMyAlVBagUSA0JVUnIFEgNTRk9AAUgBmAEC&hl=en-US"


def test_manual_google_flights_url_rejects_unrelated_hosts() -> None:
    try:
        normalize_google_flights_url("https://example.com/flights?q=test")
    except ValueError as exc:
        assert "Google Flights" in str(exc)
    else:
        raise AssertionError("Expected unrelated host to be rejected.")
