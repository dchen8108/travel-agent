from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime

from app.models.base import BookingEmailEventStatus
from app.services.bookings import BookingCandidate, record_booking
from app.models.gmail_integration import GmailIntegrationConfig
from app.services.booking_email_ingest import loggable_debug_fields, process_gmail_booking_message
from app.services.booking_extraction import (
    BookingEmailExtraction,
    BookingEmailLeg,
    BookingEmailSegment,
    BookingExtractionError,
    prepare_booking_email_body,
)
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
    stops: str = "nonstop",
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
                "stops": stops,
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
    assert not result.created_unlinked_bookings


def test_booking_email_ingest_ignores_sender_outside_allowlist_without_llm(repository: Repository, monkeypatch) -> None:
    def should_not_extract(**_: object) -> None:
        raise AssertionError("LLM extraction should not be called for sender-filtered emails")

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        should_not_extract,
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="sender-filtered-1",
            subject="Your flight booking confirmation",
            body_text="Confirmation code ABC123",
        ),
        config=GmailIntegrationConfig(allowed_from_addresses=["forwarder@example.com"]),
    )

    assert result.event.processing_status == BookingEmailEventStatus.IGNORED
    assert result.event.email_kind == "not_booking"
    assert result.event.notes == "Ignored because sender bookings@example-airline.com is not in allowed_from_addresses."
    assert not result.created_bookings
    assert not result.created_unlinked_bookings


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
    assert len(result.created_unlinked_bookings) == 1
    assert result.created_unlinked_bookings[0].source == "gmail"


def test_booking_email_ingest_collapses_connecting_itinerary_into_single_booking(repository: Repository, monkeypatch) -> None:
    trip_instance_id = _seed_trip(
        repository,
        anchor_date=date(2026, 4, 22),
        origin_airports="BUR",
        destination_airports="SEA",
        airlines="Alaska",
        start_time="07:00",
        end_time="13:00",
        stops="1_stop",
    )

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(
            email_kind="booking_confirmation",
            confidence=0.98,
            record_locator="CON123",
            total_price="221.40",
            legs=[
                BookingEmailLeg(
                    airline="AS",
                    origin_airport="BUR",
                    destination_airport="SFO",
                    departure_date="2026-04-22",
                    departure_time="08:00",
                    arrival_time="09:25",
                    flight_number="123",
                ),
                BookingEmailLeg(
                    airline="AS",
                    origin_airport="SFO",
                    destination_airport="SEA",
                    departure_date="2026-04-22",
                    departure_time="10:15",
                    arrival_time="12:20",
                    flight_number="456",
                ),
            ],
        ),
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-connecting",
            subject="Your flight booking confirmation",
            body_text="Record locator CON123",
        ),
        config=GmailIntegrationConfig(),
    )

    assert result.event.processing_status == BookingEmailEventStatus.RESOLVED_AUTO
    assert len(result.created_bookings) == 1
    booking = result.created_bookings[0]
    assert booking.trip_instance_id == trip_instance_id
    assert booking.origin_airport == "BUR"
    assert booking.destination_airport == "SEA"
    assert booking.stops == "1_stop"
    assert booking.flight_number == "123 | 456"
    assert booking.booked_price == Decimal("221.40")


def test_booking_email_ingest_includes_multiple_flight_credits_in_effective_price(repository: Repository, monkeypatch) -> None:
    trip_instance_id = _seed_trip(
        repository,
        anchor_date=date(2026, 4, 22),
        origin_airports="LAX",
        destination_airports="SFO",
        airlines="Southwest",
        start_time="05:00",
        end_time="09:00",
    )

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(
            email_kind="booking_confirmation",
            confidence=0.97,
            record_locator="CRED99",
            cash_paid="23.40",
            flight_credits_applied="100.00",
            total_price="123.40",
            segments=[
                {
                    "airline": "WN",
                    "origin_airport": "LAX",
                    "destination_airport": "SFO",
                    "departure_date": "2026-04-22",
                    "departure_time": "06:45",
                    "arrival_time": "08:05",
                    "stops": "nonstop",
                    "flight_number": "2426",
                }
            ],
            legs=[],
        ),
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-multi-credit",
            subject="Your booking confirmation",
            body_text="Record locator CRED99",
        ),
        config=GmailIntegrationConfig(),
    )

    assert result.event.processing_status == BookingEmailEventStatus.RESOLVED_AUTO
    assert len(result.created_bookings) == 1
    booking = result.created_bookings[0]
    assert booking.trip_instance_id == trip_instance_id
    assert booking.booked_price == Decimal("123.40")
    assert "Included $100 flight credit." in booking.notes


def test_booking_email_ingest_values_points_at_one_cent_each(repository: Repository, monkeypatch) -> None:
    trip_instance_id = _seed_trip(
        repository,
        anchor_date=date(2026, 4, 22),
        origin_airports="LAX",
        destination_airports="SFO",
        airlines="Southwest",
        start_time="05:00",
        end_time="09:00",
    )

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(
            email_kind="booking_confirmation",
            confidence=0.97,
            record_locator="PTS55",
            cash_paid="5.60",
            points_used=5500,
            total_price="60.60",
            segments=[
                {
                    "airline": "WN",
                    "origin_airport": "LAX",
                    "destination_airport": "SFO",
                    "departure_date": "2026-04-22",
                    "departure_time": "06:45",
                    "arrival_time": "08:05",
                    "stops": "nonstop",
                    "flight_number": "2426",
                }
            ],
            legs=[],
        ),
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-points",
            subject="Your reward booking confirmation",
            body_text="Record locator PTS55",
        ),
        config=GmailIntegrationConfig(),
    )

    assert result.event.processing_status == BookingEmailEventStatus.RESOLVED_AUTO
    assert len(result.created_bookings) == 1
    booking = result.created_bookings[0]
    assert booking.trip_instance_id == trip_instance_id
    assert booking.booked_price == Decimal("60.60")
    assert "Redeemed 5,500 points valued at $55." in booking.notes


def test_booking_email_ingest_turns_round_trip_email_into_two_bookings(repository: Repository, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(
            email_kind="booking_confirmation",
            confidence=0.94,
            record_locator="ROUND1",
            total_price="312.20",
            legs=[
                BookingEmailLeg(
                    airline="WN",
                    origin_airport="LAX",
                    destination_airport="SFO",
                    departure_date="2026-04-22",
                    departure_time="06:45",
                    arrival_time="08:05",
                    flight_number="2426",
                ),
                BookingEmailLeg(
                    airline="WN",
                    origin_airport="SFO",
                    destination_airport="LAX",
                    departure_date="2026-04-25",
                    departure_time="19:40",
                    arrival_time="21:05",
                    flight_number="2801",
                ),
            ],
        ),
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-roundtrip",
            subject="Your round trip booking confirmation",
            body_text="Record locator ROUND1",
        ),
        config=GmailIntegrationConfig(),
    )

    assert result.event.processing_status == BookingEmailEventStatus.NEEDS_RESOLUTION
    assert not result.created_bookings
    assert len(result.created_unlinked_bookings) == 2
    first, second = result.created_unlinked_bookings
    assert (first.origin_airport, first.destination_airport, first.stops) == ("LAX", "SFO", "nonstop")
    assert (second.origin_airport, second.destination_airport, second.stops) == ("SFO", "LAX", "nonstop")


def test_booking_email_ingest_prefers_explicit_segments_for_round_trip(repository: Repository, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(
            email_kind="booking_confirmation",
            confidence=0.97,
            record_locator="SEG123",
            total_price="312.20",
            segments=[
                {
                    "airline": "WN",
                    "origin_airport": "LAX",
                    "destination_airport": "SFO",
                    "departure_date": "2026-04-22",
                    "departure_time": "06:45",
                    "arrival_time": "08:05",
                    "stops": "nonstop",
                    "flight_number": "2426",
                },
                {
                    "airline": "WN",
                    "origin_airport": "SFO",
                    "destination_airport": "LAX",
                    "departure_date": "2026-04-25",
                    "departure_time": "19:40",
                    "arrival_time": "21:05",
                    "stops": "nonstop",
                    "flight_number": "2801",
                },
            ],
            legs=[],
        ),
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-roundtrip-segments",
            subject="Your round trip booking confirmation",
            body_text="Record locator SEG123",
        ),
        config=GmailIntegrationConfig(),
    )

    assert result.event.processing_status == BookingEmailEventStatus.NEEDS_RESOLUTION
    assert not result.created_bookings
    assert len(result.created_unlinked_bookings) == 2
    first, second = result.created_unlinked_bookings
    assert first.flight_number == "2426"
    assert second.flight_number == "2801"
    assert first.record_locator == "SEG123"
    assert second.record_locator == "SEG123"


def test_booking_email_ingest_enriches_explicit_segment_with_shared_fare_and_leg_flight_numbers(repository: Repository, monkeypatch) -> None:
    trip_instance_id = _seed_trip(
        repository,
        anchor_date=date(2026, 6, 1),
        origin_airports="LAX",
        destination_airports="BUR",
        airlines="Alaska",
        start_time="10:00",
        end_time="21:00",
        stops="1_stop",
    )

    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: BookingEmailExtraction(
            email_kind="booking_confirmation",
            confidence=0.97,
            record_locator="WUYQTV",
            total_price="0.00",
            segments=[
                {
                    "airline": "AS",
                    "origin_airport": "LAX",
                    "destination_airport": "BUR",
                    "departure_date": "2026-06-01",
                    "departure_time": "11:12",
                    "arrival_time": "19:34",
                    "stops": "1_stop",
                    "flight_number": "",
                    "fare_class": "unknown",
                }
            ],
            legs=[
                {
                    "airline": "AS",
                    "origin_airport": "LAX",
                    "destination_airport": "SEA",
                    "departure_date": "2026-06-01",
                    "departure_time": "11:12",
                    "arrival_time": "15:47",
                    "flight_number": "1484",
                    "fare_class": "main",
                },
                {
                    "airline": "AS",
                    "origin_airport": "SEA",
                    "destination_airport": "BUR",
                    "departure_date": "2026-06-01",
                    "departure_time": "16:59",
                    "arrival_time": "19:34",
                    "flight_number": "530",
                    "fare_class": "main",
                },
            ],
        ),
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-enriched-segment",
            subject="Updated itinerary confirmation",
            body_text="Record locator WUYQTV",
        ),
        config=GmailIntegrationConfig(),
    )

    assert result.event.processing_status in {
        BookingEmailEventStatus.RESOLVED_AUTO,
        BookingEmailEventStatus.NEEDS_RESOLUTION,
    }
    created = result.created_bookings or result.created_unlinked_bookings
    assert len(created) == 1
    booking = created[0]
    assert booking.flight_number == "1484 | 530"
    assert booking.fare_class == "economy"


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
    assert len(result.created_unlinked_bookings) == 1
    assert result.created_unlinked_bookings[0].auto_link_enabled is False
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
        lambda **_: (_ for _ in ()).throw(BookingExtractionError("quota exceeded", retryable=True)),
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
            BookingExtractionError(
                "Request too large for gpt-5.4. The input or output tokens must be reduced.",
                retryable=False,
            )
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


def test_booking_email_ingest_supports_anc_segment(repository: Repository, monkeypatch) -> None:
    trip_instance_id = _seed_trip(
        repository,
        anchor_date=date(2026, 6, 1),
        origin_airports="ANC",
        destination_airports="BUR",
        airlines="Alaska",
        start_time="10:00",
        end_time="21:00",
        stops="1_stop",
    )

    extraction = BookingEmailExtraction(
        email_kind="booking_confirmation",
        confidence=0.98,
        record_locator="WUYQTV",
        segments=[
            BookingEmailSegment(
                airline="AS",
                origin_airport="ANC",
                destination_airport="BUR",
                departure_date="2026-06-01",
                departure_time="11:12",
                arrival_time="19:34",
                arrival_day_offset=0,
                stops="1_stop",
                fare_class="main",
            )
        ],
    )
    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: extraction,
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-anc",
            subject="Fwd: Confirmation Letter - WUYQTV 06/01 - from Alaska Airlines",
            body_text="ANC to BUR",
        ),
        config=GmailIntegrationConfig(),
    )

    assert result.event.processing_status in {
        BookingEmailEventStatus.RESOLVED_AUTO,
        BookingEmailEventStatus.NEEDS_RESOLUTION,
    }
    assert result.event.retryable is True
    assert len(result.created_bookings) + len(result.created_unlinked_bookings) == 1
    booking = (result.created_bookings or result.created_unlinked_bookings)[0]
    assert booking.origin_airport == "ANC"
    if result.created_bookings:
        assert result.created_bookings[0].trip_instance_id == trip_instance_id


def test_booking_email_ingest_records_terminal_error_for_invalid_booking_candidate(
    repository: Repository, monkeypatch
) -> None:
    extraction = BookingEmailExtraction(
        email_kind="booking_confirmation",
        confidence=0.99,
        record_locator="BAD123",
        segments=[
            BookingEmailSegment(
                airline="AS",
                origin_airport="ZZZ",
                destination_airport="BUR",
                departure_date="2026-06-01",
                departure_time="11:12",
                arrival_time="19:34",
                arrival_day_offset=0,
                stops="1_stop",
                fare_class="main",
            )
        ],
    )
    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: extraction,
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-invalid-candidate",
            subject="Fwd: Confirmation Letter - BAD123",
            body_text="ZZZ to BUR",
        ),
        config=GmailIntegrationConfig(),
    )

    assert result.event.processing_status == BookingEmailEventStatus.ERROR
    assert result.event.retryable is False
    assert "Booking import failed validation" in result.event.notes
    assert "Choose a supported airport." in result.event.notes
    assert not result.created_bookings
    assert not result.created_unlinked_bookings


def test_booking_email_ingest_propagates_unexpected_extraction_errors(repository: Repository, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.booking_email_ingest.extract_booking_email",
        lambda **_: (_ for _ in ()).throw(ValueError("bad extraction fixture")),
    )

    message = _gmail_message(
        message_id="msg-unexpected-error",
        subject="Fwd: You're going to Burbank",
        body_text="Very long forwarded body",
    )

    try:
        process_gmail_booking_message(repository, message=message, config=GmailIntegrationConfig())
    except ValueError as exc:
        assert str(exc) == "bad extraction fixture"
    else:
        raise AssertionError("Expected unexpected extraction errors to propagate")


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


def test_booking_email_ingest_cancels_existing_multi_stop_booking(repository: Repository, monkeypatch) -> None:
    trip_instance_id = _seed_trip(
        repository,
        anchor_date=date(2026, 6, 8),
        origin_airports="BUR",
        destination_airports="SEA",
        airlines="Alaska",
        start_time="07:00",
        end_time="13:00",
        stops="1_stop",
    )

    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="AS",
            origin_airport="BUR",
            destination_airport="SEA",
            departure_date=date(2026, 6, 8),
            departure_time="08:00",
            arrival_time="12:20",
            booked_price=Decimal("221.40"),
            record_locator="MULTI1",
            stops="1_stop",
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
            confidence=0.96,
            record_locator="MULTI1",
            legs=[
                BookingEmailLeg(
                    airline="AS",
                    origin_airport="BUR",
                    destination_airport="SFO",
                    departure_date="2026-06-08",
                    departure_time="08:00",
                    arrival_time="09:25",
                    leg_status="cancelled",
                ),
                BookingEmailLeg(
                    airline="AS",
                    origin_airport="SFO",
                    destination_airport="SEA",
                    departure_date="2026-06-08",
                    departure_time="10:15",
                    arrival_time="12:20",
                    leg_status="cancelled",
                ),
            ],
        ),
    )

    result = process_gmail_booking_message(
        repository,
        message=_gmail_message(
            message_id="msg-cancel-multistop",
            subject="Your itinerary has been canceled",
            body_text="Record locator MULTI1",
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
