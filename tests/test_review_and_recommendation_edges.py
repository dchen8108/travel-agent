from __future__ import annotations

from datetime import datetime

from app.models.base import EmailParsedStatus, ReviewStatus, SegmentType
from app.models.email_event import EmailEvent
from app.models.fare_observation import FareObservation
from app.models.review_item import ReviewItem
from app.models.tracker import Tracker
from app.ingestion.google_flights_email_parser import ParsedGoogleFlightsEmail, ParsedGoogleFlightsObservation
from app.ingestion.observation_matcher import match_observations_to_trackers
from app.services.recommendations import history_totals_by_trip
from app.services.review import build_review_contexts, refresh_event_statuses


def test_refresh_event_statuses_keeps_unmatched_events_unmatched() -> None:
    events = [
        EmailEvent(
            email_event_id="mail_1",
            source_message_id="msg_1",
            received_at=datetime(2026, 3, 31, 8, 0).astimezone(),
            subject="No matches",
            parsed_status=EmailParsedStatus.UNMATCHED,
            imported_email_path="imported_emails/mail_1.eml",
        )
    ]

    refresh_event_statuses(events, [])

    assert events[0].parsed_status == EmailParsedStatus.UNMATCHED


def test_build_review_contexts_ignores_resolved_items() -> None:
    event = EmailEvent(
        email_event_id="mail_1",
        source_message_id="msg_1",
        received_at=datetime(2026, 3, 31, 8, 0).astimezone(),
        subject="Needs review",
        parsed_status=EmailParsedStatus.NEEDS_REVIEW,
        imported_email_path="imported_emails/mail_1.eml",
    )
    resolved_item = ReviewItem(
        review_item_id="rev_1",
        email_event_id=event.email_event_id,
        observed_route="LAX to JFK",
        status=ReviewStatus.RESOLVED,
    )

    contexts = build_review_contexts([event], [resolved_item])

    assert contexts == []


def test_history_totals_do_not_mix_different_import_batches() -> None:
    observed_at = datetime(2026, 3, 31, 8, 0).astimezone()
    primary_tracker = Tracker(
        tracker_id="trk_primary",
        trip_instance_id="trip_1",
        segment_type=SegmentType.OUTBOUND,
        origin_airport="LAX",
        destination_airport="JFK",
        travel_date="2026-06-24",
        google_flights_url="https://example.com/primary",
    )
    backup_tracker = Tracker(
        tracker_id="trk_backup",
        trip_instance_id="trip_1",
        segment_type=SegmentType.OUTBOUND,
        origin_airport="LAX",
        destination_airport="JFK",
        travel_date="2026-06-30",
        google_flights_url="https://example.com/backup",
    )
    observations = [
        FareObservation(
            observation_id="obs_1",
            tracker_id=primary_tracker.tracker_id,
            trip_instance_id="trip_1",
            segment_type=SegmentType.OUTBOUND,
            source_id="email_a",
            observed_at=observed_at,
            price=320,
        ),
        FareObservation(
            observation_id="obs_2",
            tracker_id=backup_tracker.tracker_id,
            trip_instance_id="trip_1",
            segment_type=SegmentType.OUTBOUND,
            source_id="email_a",
            observed_at=observed_at,
            price=250,
        ),
        FareObservation(
            observation_id="obs_3",
            tracker_id=primary_tracker.tracker_id,
            trip_instance_id="trip_1",
            segment_type=SegmentType.OUTBOUND,
            source_id="email_b",
            observed_at=observed_at,
            price=280,
        ),
    ]

    history = history_totals_by_trip(
        observations,
        {primary_tracker.tracker_id: primary_tracker, backup_tracker.tracker_id: backup_tracker},
    )

    assert sorted(history["trip_1"]) == [250, 280]


def test_nonstop_only_trackers_do_not_match_explicit_stop_observations() -> None:
    observed_at = datetime(2026, 3, 31, 8, 0).astimezone()
    tracker = Tracker(
        tracker_id="trk_nonstop",
        trip_instance_id="trip_1",
        segment_type=SegmentType.OUTBOUND,
        detail_rank=1,
        detail_weekday="Monday",
        detail_time_start="06:00",
        detail_time_end="10:00",
        detail_airline="Alaska",
        detail_nonstop_only=True,
        origin_airport="BUR",
        destination_airport="SFO",
        travel_date="2026-06-01",
        google_flights_url="https://example.com/nonstop",
    )
    parsed_email = ParsedGoogleFlightsEmail(
        message_id="msg_1",
        subject="Tracked flight changed",
        received_at=observed_at,
        plain_text="",
        html_text=None,
        sections=[],
        observations=[
            ParsedGoogleFlightsObservation(
                route_text="Burbank to San Francisco",
                travel_date=tracker.travel_date,
                airline="Alaska",
                origin_airport="BUR",
                destination_airport="SFO",
                price=120,
                previous_price=135,
                price_direction="dropped",
                is_nonstop=False,
                time_line="7:00 AM – 8:30 AM",
                detail_line="Alaska · 1 stop · BUR–SFO",
                flight_url="https://example.com/obs",
            )
        ],
    )

    result = match_observations_to_trackers(parsed_email, [tracker])

    assert result.observations == []
    assert len(result.review_items) == 1
