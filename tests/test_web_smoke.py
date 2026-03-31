from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.base import TrackerStatus
from app.models.program import Program
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance
from app.settings import Settings
from app.storage.repository import Repository
from app.time_slots import RankedTimeSlot, serialize_time_slot_rankings
from app.web import get_repository


def test_core_pages_render_with_empty_state(tmp_path: Path) -> None:
    repository = Repository(
        Settings(
            data_dir=tmp_path / "data",
            imported_email_dir=tmp_path / "data" / "imported_emails",
            templates_dir=Path("app/templates"),
            static_dir=Path("app/static"),
        )
    )
    repository.ensure_data_dir()
    app.dependency_overrides[get_repository] = lambda: repository
    client = TestClient(app)

    try:
        for path in ["/", "/rules", "/trackers", "/imports", "/review", "/bookings/new"]:
            response = client.get(path)
            assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_web_happy_path_import_and_booking(tmp_path: Path) -> None:
    repository = Repository(
        Settings(
            data_dir=tmp_path / "data",
            imported_email_dir=tmp_path / "data" / "imported_emails",
            templates_dir=Path("app/templates"),
            static_dir=Path("app/static"),
        )
    )
    repository.ensure_data_dir()
    seed_jfk_trip(repository)
    app.dependency_overrides[get_repository] = lambda: repository
    client = TestClient(app)
    fixture = Path(__file__).parent / "fixtures" / "google_flights_sample.eml"

    try:
        response = client.post(
            "/imports/upload",
            files={"email_file": ("google.eml", fixture.read_bytes(), "message/rfc822")},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert len(repository.load_fare_observations()) == 2

        detail = client.get("/trips/trip_jfk")
        assert detail.status_code == 200
        assert "LAX → JFK" in detail.text

        booking_response = client.post(
            "/bookings",
            data={"trip_instance_id": "trip_jfk", "booked_price": "650", "fare_type": "Flexible"},
            follow_redirects=False,
        )
        assert booking_response.status_code == 303
        refreshed = client.get("/trips/trip_jfk")
        assert "rebook" in refreshed.text.lower()
    finally:
        app.dependency_overrides.clear()


def test_invalid_ids_return_404(tmp_path: Path) -> None:
    repository = Repository(
        Settings(
            data_dir=tmp_path / "data",
            imported_email_dir=tmp_path / "data" / "imported_emails",
            templates_dir=Path("app/templates"),
            static_dir=Path("app/static"),
        )
    )
    repository.ensure_data_dir()
    app.dependency_overrides[get_repository] = lambda: repository
    client = TestClient(app)

    try:
        assert client.get("/trips/missing-trip").status_code == 404
        assert client.post("/trackers/missing-tracker/mark-enabled").status_code == 404
        assert client.post("/review/missing-review/ignore").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_booking_rejects_foreign_tracker_ids(tmp_path: Path) -> None:
    repository = Repository(
        Settings(
            data_dir=tmp_path / "data",
            imported_email_dir=tmp_path / "data" / "imported_emails",
            templates_dir=Path("app/templates"),
            static_dir=Path("app/static"),
        )
    )
    repository.ensure_data_dir()
    seed_jfk_trip(repository)
    app.dependency_overrides[get_repository] = lambda: repository
    client = TestClient(app)

    try:
        response = client.post(
            "/bookings",
            data={"trip_instance_id": "trip_jfk", "tracker_id": "trk_foreign", "booked_price": "650", "fare_type": "Flexible"},
            follow_redirects=False,
        )
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


def seed_jfk_trip(repository: Repository) -> None:
    program = Program(
        program_id="prog_jfk",
        program_name="LAX to JFK test",
        origin_airports="LAX",
        destination_airports="JFK",
        time_slot_rankings=serialize_time_slot_rankings(
            [
                RankedTimeSlot(weekday="Wednesday", start_time="21:00", end_time="22:00"),
                RankedTimeSlot(weekday="Wednesday", start_time="22:00", end_time="23:30"),
            ]
        ),
        airlines="American",
        fare_preference="flexible",
        nonstop_only=True,
        lookahead_weeks=8,
        rebook_alert_threshold=20,
    )
    trip = TripInstance(
        trip_instance_id="trip_jfk",
        program_id=program.program_id,
        origin_airport="LAX",
        destination_airport="JFK",
        outbound_date="2026-06-24",
        outbound_tracker_id="trk_primary",
    )
    repository.save_programs([program])
    repository.save_trip_instances([trip])
    repository.save_trackers(
        [
            Tracker(
                tracker_id="trk_primary",
                trip_instance_id=trip.trip_instance_id,
                segment_type="outbound",
                slot_rank=1,
                slot_weekday="Wednesday",
                slot_time_start="21:00",
                slot_time_end="22:00",
                origin_airport="LAX",
                destination_airport="JFK",
                travel_date="2026-06-24",
                tracking_status=TrackerStatus.TRACKING_ENABLED,
                google_flights_url="https://example.com/primary",
            ),
            Tracker(
                tracker_id="trk_backup",
                trip_instance_id=trip.trip_instance_id,
                segment_type="outbound",
                slot_rank=2,
                slot_weekday="Wednesday",
                slot_time_start="22:00",
                slot_time_end="23:30",
                origin_airport="LAX",
                destination_airport="JFK",
                travel_date="2026-06-24",
                tracking_status=TrackerStatus.TRACKING_ENABLED,
                google_flights_url="https://example.com/backup",
            ),
        ]
    )
