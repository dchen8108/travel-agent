from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from app.models.base import BookingStatus, ProgramWeekday, TrackerStatus, TripStatus
from app.models.booking import Booking
from app.models.program import Program
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance
from app.services.email_import import import_email_payload
from app.services.workflows import recompute_and_persist
from app.settings import Settings
from app.storage.repository import Repository

FIXTURE = Path(__file__).parent / "fixtures" / "google_flights_sample.eml"


def test_import_email_is_idempotent_and_recomputes_trip_state(tmp_path: Path) -> None:
    repository = build_repository(tmp_path)
    seed_jfk_trip(repository)
    payload = FIXTURE.read_bytes()

    first_event = import_email_payload(repository, FIXTURE.name, payload)
    second_event = import_email_payload(repository, FIXTURE.name, payload)

    email_events = repository.load_email_events()
    observations = repository.load_fare_observations()
    review_items = repository.load_review_items()
    trackers = {tracker.tracker_id: tracker for tracker in repository.load_trackers()}
    trip = repository.load_trip_instances()[0]

    assert first_event.email_event_id == second_event.email_event_id
    assert len(email_events) == 1
    assert len(observations) == 4
    assert len(review_items) == 1
    assert trackers["trk_out"].tracking_status == TrackerStatus.SIGNAL_RECEIVED
    assert trackers["trk_out"].latest_observed_price == 334
    assert trackers["trk_ret"].latest_observed_price == 269
    assert trip.best_price == 603
    assert trip.status == TripStatus.BOOK_NOW
    assert trip.best_airline == "American"


def test_booking_recompute_can_trigger_rebook(tmp_path: Path) -> None:
    repository = build_repository(tmp_path)
    seed_jfk_trip(repository)
    import_email_payload(repository, FIXTURE.name, FIXTURE.read_bytes())

    booking = Booking(
        booking_id="book_1",
        trip_instance_id="trip_jfk",
        airline="American",
        fare_type="Flexible",
        booked_price=650,
        booked_at=datetime(2026, 4, 1, 9, 0).astimezone(),
        status=BookingStatus.ACTIVE,
    )
    repository.save_bookings([booking])
    recompute_and_persist(repository)

    trip = repository.load_trip_instances()[0]
    assert trip.status == TripStatus.REBOOK
    assert "below your booked total" in trip.recommendation_reason


def build_repository(tmp_path: Path) -> Repository:
    data_dir = tmp_path / "data"
    settings = Settings(
        data_dir=data_dir,
        imported_email_dir=data_dir / "imported_emails",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    repository = Repository(settings)
    repository.ensure_data_dir()
    return repository


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
        outbound_date=date(2026, 6, 24),
        return_date=date(2026, 6, 30),
        outbound_tracker_id="trk_out",
        return_tracker_id="trk_ret",
    )
    outbound_tracker = Tracker(
        tracker_id="trk_out",
        trip_instance_id=trip.trip_instance_id,
        segment_type="outbound",
        origin_airport="LAX",
        destination_airport="JFK",
        travel_date=trip.outbound_date,
        tracking_status=TrackerStatus.TRACKING_ENABLED,
        google_flights_url="https://example.com/outbound",
    )
    return_tracker = Tracker(
        tracker_id="trk_ret",
        trip_instance_id=trip.trip_instance_id,
        segment_type="return",
        origin_airport="JFK",
        destination_airport="LAX",
        travel_date=trip.return_date,
        tracking_status=TrackerStatus.TRACKING_ENABLED,
        google_flights_url="https://example.com/return",
    )
    repository.save_programs([program])
    repository.save_trip_instances([trip])
    repository.save_trackers([outbound_tracker, return_tracker])
