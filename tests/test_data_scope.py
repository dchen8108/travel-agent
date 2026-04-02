from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.models.base import AppState, DataScope, TripInstanceKind, TravelState, utcnow
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.services.bookings import BookingCandidate, record_booking
from app.services.dashboard import load_snapshot
from app.settings import Settings
from app.storage.repository import Repository


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )


def test_load_snapshot_hides_test_scoped_rows_by_default(tmp_path: Path) -> None:
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
    repository.save_trips([live_trip, test_trip])

    snapshot = load_snapshot(repository, recompute=False)

    assert [trip.trip_id for trip in snapshot.trips] == ["trip_live"]


def test_record_booking_ignores_test_trackers_when_processing_disabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = Repository(settings)
    repository.ensure_data_dir()
    repository.save_app_state(AppState(show_test_data=False, process_test_data=False))

    repository.save_trip_instances(
        [
            TripInstance(
                trip_instance_id="inst_test",
                trip_id="trip_test",
                display_label="QA Hidden Trip",
                anchor_date=date(2026, 4, 20),
                data_scope=DataScope.TEST,
                instance_kind=TripInstanceKind.STANDALONE,
                travel_state=TravelState.OPEN,
            )
        ]
    )
    repository.save_trackers(
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
