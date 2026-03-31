from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.email_import import import_google_flights_email
from app.services.trips import save_trip
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


FIXTURE = Path(__file__).parent / "fixtures" / "google_flights_sample.eml"


def test_import_google_flights_email_matches_supported_tracker(repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="SFO to BUR test",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 6, 4),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "SFO",
                "destination_airports": "BUR",
                "airlines": "Southwest",
                "day_offset": 0,
                "start_time": "07:00",
                "end_time": "23:00",
            }
        ],
    )
    sync_and_persist(repository, today=date(2026, 5, 1))

    result = import_google_flights_email(
        repository,
        payload=FIXTURE.read_bytes(),
        filename="google.eml",
    )
    sync_and_persist(repository, today=date(2026, 5, 1))

    assert result.matched_count >= 1
    assert len(repository.load_fare_observations()) >= 1


def test_ambiguous_tracker_matches_are_ignored(repository: Repository) -> None:
    for label in ("SFO to BUR A", "SFO to BUR B"):
        save_trip(
            repository,
            trip_id=None,
            label=label,
            trip_kind="one_time",
            active=True,
            anchor_date=date(2026, 6, 4),
            anchor_weekday="",
            route_option_payloads=[
                {
                        "origin_airports": "SFO",
                        "destination_airports": "BUR",
                        "airlines": "Southwest",
                        "day_offset": 0,
                        "start_time": "07:00",
                        "end_time": "23:00",
                    }
                ],
            )
    sync_and_persist(repository, today=date(2026, 5, 1))

    result = import_google_flights_email(
        repository,
        payload=FIXTURE.read_bytes(),
        filename="google.eml",
    )

    assert result.matched_count == 0
    assert len(repository.load_fare_observations()) == 0


def test_duplicate_email_import_is_ignored(repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="SFO to BUR duplicate import",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 6, 4),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "SFO",
                "destination_airports": "BUR",
                "airlines": "Southwest",
                "day_offset": 0,
                "start_time": "07:00",
                "end_time": "23:00",
            }
        ],
    )
    sync_and_persist(repository, today=date(2026, 5, 1))

    first = import_google_flights_email(repository, payload=FIXTURE.read_bytes(), filename="google.eml")
    second = import_google_flights_email(repository, payload=FIXTURE.read_bytes(), filename="google.eml")

    assert first.email_event.email_event_id == second.email_event.email_event_id
    assert len(repository.load_email_events()) == 1
