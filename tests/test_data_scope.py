from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.models.base import AppState, DataScope, TripInstanceKind, utcnow
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.services.bookings import BookingCandidate, record_booking
from app.services.dashboard_snapshot import load_live_snapshot, load_persisted_snapshot
from app.services.trips import save_trip
from app.settings import Settings
from app.storage.repository import Repository


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )


def test_load_persisted_snapshot_hides_test_scoped_rows_by_default(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = Repository(settings)
    repository.ensure_data_dir()
    repository.save_app_state(AppState(show_test_data=False, process_test_data=False))

    live_trip = Trip(
        trip_id="trip_live",
        label="Live Trip",
        trip_kind="one_time",
        data_scope=DataScope.LIVE,
        anchor_date=date(2026, 4, 20),
    )
    test_trip = Trip(
        trip_id="trip_test",
        label="QA Hidden Trip",
        trip_kind="one_time",
        data_scope=DataScope.TEST,
        anchor_date=date(2026, 4, 21),
    )
    repository.upsert_trip(live_trip)
    repository.upsert_trip(test_trip)

    snapshot = load_persisted_snapshot(repository)

    assert [trip.trip_id for trip in snapshot.trips] == ["trip_live"]


def test_record_booking_ignores_test_trackers_when_processing_disabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = Repository(settings)
    repository.ensure_data_dir()
    repository.save_app_state(AppState(show_test_data=False, process_test_data=False))

    repository.replace_trip_instances(
        [
            TripInstance(
                trip_instance_id="inst_test",
                trip_id="trip_test",
                display_label="QA Hidden Trip",
                anchor_date=date(2026, 4, 20),
                data_scope=DataScope.TEST,
                instance_kind=TripInstanceKind.STANDALONE,
            )
        ]
    )
    repository.replace_trackers(
        [
            Tracker(
                tracker_id="trk_test",
                trip_instance_id="inst_test",
                route_option_id="opt_test",
                rank=1,
                data_scope=DataScope.TEST,
                origin_airports="BUR",
                destination_airports="SFO",
                airlines="AS",
                day_offset=0,
                travel_date=date(2026, 4, 20),
                start_time="06:00",
                end_time="10:00",
                definition_signature="sig_test",
            )
        ]
    )

    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Alaska",
            origin_airport="BUR",
            destination_airport="SFO",
            departure_date=date(2026, 4, 20),
            departure_time="07:15",
            arrival_time="08:35",
            booked_price=Decimal("119.00"),
            record_locator="LIVE123",
        ),
    )

    assert booking is None
    assert unmatched is not None
    assert unmatched.data_scope == DataScope.LIVE


def test_load_live_snapshot_reconciles_and_persists_instances(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = Repository(settings)
    repository.ensure_data_dir()

    trip = save_trip(
        repository,
        trip_id=None,
        label="Weekly commute",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
        trip_group_ids=[],
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "WN",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
                "fare_class_policy": "include_basic",
            }
        ],
    )

    persisted = load_persisted_snapshot(repository)
    assert persisted.trip_instances == []

    live = load_live_snapshot(repository, today=date(2026, 4, 6))
    live_trip_instances = [item for item in live.trip_instances if item.trip_id == trip.trip_id]
    assert len(live_trip_instances) == 16

    stored_trip_instances = [item for item in repository.load_trip_instances() if item.trip_id == trip.trip_id]
    assert len(stored_trip_instances) == 16
