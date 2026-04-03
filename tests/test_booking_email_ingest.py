from __future__ import annotations

from datetime import date, datetime

from app.models.base import BookingEmailEventStatus
from app.services.bookings import BookingCandidate, record_booking
from app.models.gmail_integration import GmailIntegrationConfig
from app.services.booking_email_ingest import loggable_debug_fields, process_gmail_booking_message
from app.services.booking_extraction import BookingEmailExtraction, BookingEmailLeg, prepare_booking_email_body
from app.services.gmail_client import GmailMessage
from app.services.trips import save_trip
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


def _seed_trip(
    repository: Repository,
    *,
    anchor_date: date = date(2026, 4, 22),
    origin_airports: str = "BUR",
    destination_airports: str = "SFO",
    airlines: str = "Alaska",
    start_time: str = "06:00",
    end_time: str = "10:00",
) -> str:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Inbox Import Test",
        trip_kind="one_time",
        active=True,
        anchor_date=anchor_date,
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": origin_airports,
                "destination_airports": destination_airports,
                "airlines": airlines,
                "day_offset": 0,
                "start_time": start_time,
                "end_time": end_time,
            }
        ],
    )
    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    return next(item.trip_instance_id for item in snapshot.trip_instances if item.trip_id == trip.trip_id)


def _gmail_message(*, message_id: str, subject: str, body_text: str) -> GmailMessage:
    return GmailMessage(
        gmail_message_id=message_id,
        gmail_thread_id=f"thread-{message_id}",
        gmail_history_id="12345",
        from_address="bookings@example-airline.com",
        subject=subject,
        received_at=datetime(2026, 4, 1, 12, 0).astimezone(),
        body_text=body_text,
    )


def test_booking_email_ingest_ignores_clear_spam_without_llm(repository: Repository, monkeypatch) -> None:
    def should_not_extract(**_: object) -> None:
        raise AssertionError("LLM extraction should not be called for spam-gated emails")

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        should_not_extract,
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="spam-1",
            subject="Big sale this weekend",
            body_text="Unsubscribe for bonus miles and promotion details.",
        ),
        config=GmailIntegrationConfig(),
    )

    assert result.event.processing_status == BookingEmailEventStatus.IGNORED
    assert result.event.email_kind == "not_booking"
    assert not result.created_bookings
    assert not result.created_unmatched_bookings


def test_booking_email_ingest_auto_creates_booking(repository: Repository, monkeypatch) -> None:
    trip_instance_id = _seed_trip(repository)

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(
            email_kind="booking_confirmation",
            confidence=0.96,
            record_locator="ABC123",
            total_price=121,
            legs=[
                BookingEmailLeg(
                    airline="AS",
                    origin_airport="BUR",
                    destination_airport="SFO",
                    departure_date="2026-04-22",
                    departure_time="07:15",
                    arrival_time="08:40",
                )
            ],
        ),
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-1",
            subject="Your flight booking confirmation",
            body_text="Confirmation code ABC123",
        ),
        config=GmailIntegrationConfig(debug_log_model_io=True),
    )

    assert result.event.processing_status == BookingEmailEventStatus.RESOLVED_AUTO
    assert len(result.created_bookings) == 1
    booking = result.created_bookings[0]
    assert booking.trip_instance_id == trip_instance_id
    assert booking.route_option_id != ""
    assert booking.source == "gmail"
    assert booking.record_locator == "ABC123"
    assert repository.load_booking_email_events()[0].gmail_message_id == "msg-1"
    assert result.debug_fields["llm"]["prepared_body"]
    assert result.debug_fields["llm"]["parsed_output"]["record_locator"] == "ABC123"


def test_booking_email_debug_logging_redacts_model_io_by_default() -> None:
    raw_debug = {
        "llm": {
            "prepared_body": "secret booking body",
            "parsed_output": {"record_locator": "ABC123"},
            "prepared_body_chars": 18,
        },
        "matching": {"candidate_count": 1},
    }

    sanitized = loggable_debug_fields(raw_debug, include_model_io=False)

    assert "prepared_body" not in sanitized["llm"]
    assert "parsed_output" not in sanitized["llm"]
    assert sanitized["llm"]["prepared_body_chars"] == 18
    assert sanitized["matching"]["candidate_count"] == 1


def test_booking_email_ingest_creates_unmatched_when_no_tracker_matches(repository: Repository, monkeypatch) -> None:
    _seed_trip(repository)

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(
            email_kind="booking_confirmation",
            confidence=0.93,
            record_locator="DEF456",
            total_price=149,
            legs=[
                BookingEmailLeg(
                    airline="UA",
                    origin_airport="LAX",
                    destination_airport="SEA",
                    departure_date="2026-04-22",
                    departure_time="07:15",
                    arrival_time="10:10",
                )
            ],
        ),
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-2",
            subject="Trip confirmation",
            body_text="Record locator DEF456",
        ),
        config=GmailIntegrationConfig(),
    )

    assert result.event.processing_status == BookingEmailEventStatus.NEEDS_RESOLUTION
    assert not result.created_bookings
    assert len(result.created_unmatched_bookings) == 1
    assert result.created_unmatched_bookings[0].source == "gmail"


def test_booking_email_ingest_low_confidence_booking_stays_unmatched(repository: Repository, monkeypatch) -> None:
    _seed_trip(repository)

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(
            email_kind="booking_confirmation",
            confidence=0.72,
            record_locator="LOW123",
            total_price="121.40",
            legs=[
                BookingEmailLeg(
                    airline="AS",
                    origin_airport="BUR",
                    destination_airport="SFO",
                    departure_date="2026-04-22",
                    departure_time="07:15",
                    arrival_time="08:40",
                )
            ],
        ),
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-low-confidence",
            subject="Your flight booking confirmation",
            body_text="Confirmation code LOW123",
        ),
        config=GmailIntegrationConfig(min_auto_create_confidence=0.85),
    )

    assert result.event.processing_status == BookingEmailEventStatus.NEEDS_RESOLUTION
    assert not result.created_bookings
    assert len(result.created_unmatched_bookings) == 1
    assert result.created_unmatched_bookings[0].auto_link_enabled is False
    assert result.debug_fields["matching"]["auto_create_allowed"] is False



def test_booking_email_ingest_is_idempotent_for_duplicate_message(repository: Repository, monkeypatch) -> None:
    _seed_trip(repository)
    extraction = BookingEmailExtraction(
        email_kind="booking_confirmation",
        confidence=0.96,
        record_locator="ABC123",
        total_price=121,
        legs=[
            BookingEmailLeg(
                airline="AS",
                origin_airport="BUR",
                destination_airport="SFO",
                departure_date="2026-04-22",
                departure_time="07:15",
                arrival_time="08:40",
            )
        ],
    )
    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: extraction,
    )

    message = _gmail_message(
        message_id="msg-dup",
        subject="Your flight booking confirmation",
        body_text="Confirmation code ABC123",
    )
    first = process_gmail_booking_message(repository, message=message, config=GmailIntegrationConfig())
    second = process_gmail_booking_message(repository, message=message, config=GmailIntegrationConfig())

    assert len(first.created_bookings) == 1
    assert not second.created_bookings
    assert len(repository.load_bookings()) == 1
    assert len(repository.load_booking_email_events()) == 1


def test_booking_email_ingest_records_retryable_error_event(repository: Repository, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: (_ for _ in ()).throw(RuntimeError("quota exceeded")),
    )

    message = _gmail_message(
        message_id="msg-error",
        subject="Your flight booking confirmation",
        body_text="Confirmation code ABC123",
    )
    first = process_gmail_booking_message(repository, message=message, config=GmailIntegrationConfig())

    assert first.event.processing_status == BookingEmailEventStatus.ERROR
    assert "quota exceeded" in first.event.notes
    assert len(repository.load_booking_email_events()) == 1

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(
            email_kind="not_booking",
            confidence=0.7,
        ),
    )
    second = process_gmail_booking_message(repository, message=message, config=GmailIntegrationConfig())

    assert second.event.processing_status == BookingEmailEventStatus.IGNORED
    assert len(repository.load_booking_email_events()) == 1


def test_booking_email_ingest_does_not_retry_terminal_extraction_error(repository: Repository, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: (_ for _ in ()).throw(
            RuntimeError("Request too large for gpt-5.4. The input or output tokens must be reduced.")
        ),
    )

    message = _gmail_message(
        message_id="msg-terminal-error",
        subject="Fwd: You're going to Burbank",
        body_text="Very long forwarded body",
    )
    first = process_gmail_booking_message(repository, message=message, config=GmailIntegrationConfig())

    assert first.event.processing_status == BookingEmailEventStatus.ERROR
    assert first.event.retryable is False
    assert first.event.extraction_attempt_count == 1

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(email_kind="booking_confirmation", confidence=0.99),
    )
    second = process_gmail_booking_message(repository, message=message, config=GmailIntegrationConfig())

    assert second.event.processing_status == BookingEmailEventStatus.ERROR
    assert second.event.extraction_attempt_count == 1
    assert len(repository.load_booking_email_events()) == 1


def test_prepare_booking_email_body_limits_size_and_keeps_relevant_lines() -> None:
    large_body = "\n".join(
        [f"noise line {index}" for index in range(120)]
        + [
            "Confirmation code ABC123",
            "LAX to BUR",
            "Flight WN 123 departs 09:10 arrives 10:35",
            "Total paid $78.40",
        ]
        + [f"footer line {index}" for index in range(120)]
    )

    prepared = prepare_booking_email_body(large_body, max_chars=180)

    assert len(prepared) <= 180
    assert "Confirmation code ABC123" in prepared
    assert "Total paid $78.40" in prepared


def test_booking_email_ingest_cancels_existing_booking(repository: Repository, monkeypatch) -> None:
    trip_instance_id = _seed_trip(
        repository,
        anchor_date=date(2026, 6, 8),
        origin_airports="LAX",
        destination_airports="SFO",
        airlines="Southwest",
        start_time="05:00",
        end_time="09:00",
    )

    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="WN",
            origin_airport="LAX",
            destination_airport="SFO",
            departure_date=date(2026, 6, 8),
            departure_time="06:45",
            arrival_time="08:05",
            booked_price=121,
            record_locator="ABC123",
        ),
        trip_instance_id=trip_instance_id,
        source="gmail",
    )
    assert booking is not None
    assert unmatched is None

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(
            email_kind="cancellation",
            confidence=0.92,
            record_locator="ABC123",
            legs=[
                BookingEmailLeg(
                    airline="WN",
                    origin_airport="LAX",
                    destination_airport="SFO",
                    departure_date="2026-06-08",
                    departure_time="06:45",
                    arrival_time="08:05",
                    leg_status="cancelled",
                )
            ],
        ),
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-cancel",
            subject="Your flight has been canceled",
            body_text="Record locator ABC123",
        ),
        config=GmailIntegrationConfig(),
    )

    assert result.event.processing_status == BookingEmailEventStatus.RESOLVED_AUTO
    saved_booking = repository.load_bookings()[0]
    assert saved_booking.status == "cancelled"


def test_booking_email_ingest_low_confidence_cancellation_does_not_apply(repository: Repository, monkeypatch) -> None:
    trip_instance_id = _seed_trip(
        repository,
        anchor_date=date(2026, 6, 8),
        origin_airports="LAX",
        destination_airports="SFO",
        airlines="Southwest",
        start_time="05:00",
        end_time="09:00",
    )

    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="WN",
            origin_airport="LAX",
            destination_airport="SFO",
            departure_date=date(2026, 6, 8),
            departure_time="06:45",
            arrival_time="08:05",
            booked_price=121,
            record_locator="LOWCAN",
        ),
        trip_instance_id=trip_instance_id,
        source="gmail",
    )
    assert booking is not None
    assert unmatched is None

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(
            email_kind="cancellation",
            confidence=0.70,
            record_locator="LOWCAN",
            legs=[
                BookingEmailLeg(
                    airline="WN",
                    origin_airport="LAX",
                    destination_airport="SFO",
                    departure_date="2026-06-08",
                    departure_time="06:45",
                    arrival_time="08:05",
                    leg_status="cancelled",
                )
            ],
        ),
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-low-cancel",
            subject="Your flight has been canceled",
            body_text="Record locator LOWCAN",
        ),
        config=GmailIntegrationConfig(min_auto_create_confidence=0.85),
    )

    assert result.event.processing_status == BookingEmailEventStatus.NEEDS_RESOLUTION
    saved_booking = repository.load_bookings()[0]
    assert saved_booking.status == "active"
