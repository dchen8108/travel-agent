from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.base import ProgramWeekday, TrackerStatus
from app.models.program import Program
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance
from app.settings import Settings
from app.storage.repository import Repository
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
        assert len(repository.load_fare_observations()) == 4

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


def seed_jfk_trip(repository: Repository) -> None:
    program = Program(
        program_id="prog_jfk",
        program_name="LAX to JFK test",
        origin_airports="LAX",
        destination_airports="JFK",
        outbound_weekday=ProgramWeekday.WEDNESDAY,
        outbound_time_start="08:00",
        outbound_time_end="12:00",
        return_weekday=ProgramWeekday.TUESDAY,
        return_time_start="12:00",
        return_time_end="20:00",
        preferred_airlines="American",
        allowed_airlines="American",
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
        return_date="2026-06-30",
        outbound_tracker_id="trk_out",
        return_tracker_id="trk_ret",
    )
    repository.save_programs([program])
    repository.save_trip_instances([trip])
    repository.save_trackers(
        [
            Tracker(
                tracker_id="trk_out",
                trip_instance_id=trip.trip_instance_id,
                segment_type="outbound",
                origin_airport="LAX",
                destination_airport="JFK",
                travel_date="2026-06-24",
                tracking_status=TrackerStatus.TRACKING_ENABLED,
                google_flights_url="https://example.com/outbound",
            ),
            Tracker(
                tracker_id="trk_ret",
                trip_instance_id=trip.trip_instance_id,
                segment_type="return",
                origin_airport="JFK",
                destination_airport="LAX",
                travel_date="2026-06-30",
                tracking_status=TrackerStatus.TRACKING_ENABLED,
                google_flights_url="https://example.com/return",
            ),
        ]
    )
