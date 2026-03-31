from __future__ import annotations

from datetime import date

from app.services.trips import save_trip
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
