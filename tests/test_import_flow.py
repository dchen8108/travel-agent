from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from app.models.base import BookingStatus, TrackerStatus, TripStatus
from app.models.booking import Booking
from app.models.fare_observation import FareObservation
from app.models.program import Program
from app.models.tracker import Tracker
from app.models.trip_instance import TripInstance
from app.route_details import RankedRouteDetail, serialize_route_detail_rankings
from app.services.email_import import import_email_payload
from app.services.workflows import recompute_and_persist
from app.settings import Settings
from app.storage.repository import Repository

FIXTURE = Path(__file__).parent / "fixtures" / "google_flights_sample.eml"


def route_details_json(*details: RankedRouteDetail) -> str:
    return serialize_route_detail_rankings(list(details))


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
    assert len(observations) == 2
    assert len(review_items) == 3
    assert trackers["trk_out_primary"].tracking_status == TrackerStatus.SIGNAL_RECEIVED
    assert trackers["trk_out_primary"].latest_observed_price == 334
    assert trackers["trk_out_backup"].latest_observed_price == 334
    assert trip.best_price == 334
    assert trip.status == TripStatus.BOOK_NOW
    assert trip.best_airline == "American"


def test_booking_recompute_can_trigger_rebook(tmp_path: Path) -> None:
    repository = build_repository(tmp_path)
    seed_jfk_trip(repository)
    import_email_payload(repository, FIXTURE.name, FIXTURE.read_bytes())

    booking = Booking(
        booking_id="book_1",
        trip_instance_id="trip_jfk",
        tracker_id="trk_out_primary",
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
    assert "booked route option" in trip.recommendation_reason


def test_booking_recompute_uses_booked_route_option_not_cheapest_fallback(tmp_path: Path) -> None:
    repository = build_repository(tmp_path)
    seed_jfk_trip(repository)
    observed_at = datetime(2026, 4, 2, 8, 0).astimezone()
    repository.save_fare_observations(
        [
            FareObservation(
                observation_id="obs_primary",
                tracker_id="trk_out_primary",
                trip_instance_id="trip_jfk",
                segment_type="outbound",
                source_id="email_primary",
                observed_at=observed_at,
                airline="American",
                price=405,
                outbound_summary="American 9:15 PM | Primary option",
            ),
            FareObservation(
                observation_id="obs_backup",
                tracker_id="trk_out_backup",
                trip_instance_id="trip_jfk",
                segment_type="outbound",
                source_id="email_backup",
                observed_at=observed_at,
                airline="American",
                price=200,
                outbound_summary="American 10:15 PM | Backup option",
            ),
        ]
    )
    repository.save_bookings(
        [
            Booking(
                booking_id="book_2",
                trip_instance_id="trip_jfk",
                tracker_id="trk_out_primary",
                airline="American",
                fare_type="Flexible",
                booked_price=400,
                booked_at=observed_at,
                status=BookingStatus.ACTIVE,
            )
        ]
    )
    recompute_and_persist(repository)

    trip = repository.load_trip_instances()[0]
    assert trip.best_price == 200
    assert trip.status == TripStatus.BOOKED_MONITORING
    assert "monitored across your ranked route options" in trip.recommendation_reason.lower()


def test_booking_recompute_waits_for_booked_route_option_signal_before_rebook(tmp_path: Path) -> None:
    repository = build_repository(tmp_path)
    seed_jfk_trip(repository)
    observed_at = datetime(2026, 4, 2, 8, 0).astimezone()
    repository.save_fare_observations(
        [
            FareObservation(
                observation_id="obs_backup_only",
                tracker_id="trk_out_backup",
                trip_instance_id="trip_jfk",
                segment_type="outbound",
                source_id="email_backup_only",
                observed_at=observed_at,
                airline="American",
                price=200,
                outbound_summary="American 10:15 PM | Backup option",
            ),
        ]
    )
    repository.save_bookings(
        [
            Booking(
                booking_id="book_3",
                trip_instance_id="trip_jfk",
                tracker_id="trk_out_primary",
                airline="American",
                fare_type="Flexible",
                booked_price=400,
                booked_at=observed_at,
                status=BookingStatus.ACTIVE,
            )
        ]
    )
    recompute_and_persist(repository)

    trip = repository.load_trip_instances()[0]
    assert trip.best_price == 200
    assert trip.status == TripStatus.BOOKED_MONITORING
    assert "fresh price signal" in trip.recommendation_reason.lower()


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
        route_detail_rankings=route_details_json(
            RankedRouteDetail(
                origin_airport="LAX",
                destination_airport="JFK",
                weekday="Wednesday",
                start_time="21:00",
                end_time="22:00",
                airline="American",
                nonstop_only=True,
            ),
            RankedRouteDetail(
                origin_airport="LAX",
                destination_airport="JFK",
                weekday="Wednesday",
                start_time="22:00",
                end_time="23:30",
                airline="American",
                nonstop_only=True,
            ),
        ),
    )
    trip = TripInstance(
        trip_instance_id="trip_jfk",
        program_id=program.program_id,
        origin_airport="LAX",
        destination_airport="JFK",
        outbound_date=date(2026, 6, 24),
        outbound_tracker_id="trk_out_primary",
    )
    repository.save_programs([program])
    repository.save_trip_instances([trip])
    repository.save_trackers(
        [
            Tracker(
                tracker_id="trk_out_primary",
                trip_instance_id=trip.trip_instance_id,
                segment_type="outbound",
                detail_rank=1,
                detail_weekday="Wednesday",
                detail_time_start="21:00",
                detail_time_end="22:00",
                detail_airline="American",
                detail_nonstop_only=True,
                origin_airport="LAX",
                destination_airport="JFK",
                travel_date="2026-06-24",
                tracking_status=TrackerStatus.TRACKING_ENABLED,
                google_flights_url="https://example.com/outbound-primary",
            ),
            Tracker(
                tracker_id="trk_out_backup",
                trip_instance_id=trip.trip_instance_id,
                segment_type="outbound",
                detail_rank=2,
                detail_weekday="Wednesday",
                detail_time_start="22:00",
                detail_time_end="23:30",
                detail_airline="American",
                detail_nonstop_only=True,
                origin_airport="LAX",
                destination_airport="JFK",
                travel_date="2026-06-24",
                tracking_status=TrackerStatus.TRACKING_ENABLED,
                google_flights_url="https://example.com/outbound-backup",
            ),
        ]
    )
