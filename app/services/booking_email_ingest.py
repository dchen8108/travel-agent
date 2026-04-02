from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json

from app.catalog import normalize_airline_code
from app.models.base import BookingEmailEventStatus, utcnow
from app.models.booking import Booking
from app.models.booking_email_event import BookingEmailEvent
from app.models.gmail_integration import GmailIntegrationConfig
from app.models.unmatched_booking import UnmatchedBooking
from app.services.booking_extraction import BookingEmailExtraction, extract_booking_email
from app.services.bookings import BookingCandidate, record_booking
from app.services.gmail_client import GmailMessage
from app.services.ids import new_id
from app.storage.repository import Repository


@dataclass
class BookingEmailProcessResult:
    event: BookingEmailEvent
    created_bookings: list[Booking]
    created_unmatched_bookings: list[UnmatchedBooking]


def process_gmail_booking_message(
    repository: Repository,
    *,
    message: GmailMessage,
    config: GmailIntegrationConfig,
) -> BookingEmailProcessResult:
    existing_event = next(
        (event for event in repository.load_booking_email_events() if event.gmail_message_id == message.gmail_message_id),
        None,
    )
    if existing_event is not None:
        return BookingEmailProcessResult(
            event=existing_event,
            created_bookings=[],
            created_unmatched_bookings=[],
        )

    event = BookingEmailEvent(
        email_event_id=new_id("mail"),
        gmail_message_id=message.gmail_message_id,
        gmail_thread_id=message.gmail_thread_id,
        gmail_history_id=message.gmail_history_id,
        from_address=message.from_address,
        subject=message.subject,
        received_at=message.received_at,
    )
    lowered = _message_search_text(message)
    if _looks_like_non_booking(lowered, config):
        event.processing_status = BookingEmailEventStatus.IGNORED
        event.email_kind = "not_booking"
        event.notes = "Ignored by booking keyword gate."
        event.updated_at = utcnow()
        repository.append_booking_email_events([event])
        return BookingEmailProcessResult(event=event, created_bookings=[], created_unmatched_bookings=[])

    extraction = extract_booking_email(
        settings=repository.settings,
        model=config.model,
        from_address=message.from_address,
        subject=message.subject,
        body_text=message.body_text,
    )
    event.email_kind = extraction.email_kind
    event.extraction_confidence = extraction.confidence
    event.extracted_payload_json = extraction.model_dump_json(indent=2)

    if extraction.email_kind != "booking_confirmation":
        event.processing_status = BookingEmailEventStatus.IGNORED
        event.notes = _non_booking_reason(extraction)
        event.updated_at = utcnow()
        repository.append_booking_email_events([event])
        return BookingEmailProcessResult(event=event, created_bookings=[], created_unmatched_bookings=[])

    candidates = _candidates_from_extraction(extraction)
    if not candidates:
        event.processing_status = BookingEmailEventStatus.ERROR
        event.notes = "The extractor did not return any valid booking legs."
        event.updated_at = utcnow()
        repository.append_booking_email_events([event])
        return BookingEmailProcessResult(event=event, created_bookings=[], created_unmatched_bookings=[])

    created_bookings: list[Booking] = []
    created_unmatched_bookings: list[UnmatchedBooking] = []
    duplicate_count = 0
    for candidate in candidates:
        if _booking_candidate_exists(repository, candidate):
            duplicate_count += 1
            continue
        booking, unmatched = record_booking(
            repository,
            candidate,
            source="gmail",
        )
        if booking is not None:
            created_bookings.append(booking)
        if unmatched is not None:
            created_unmatched_bookings.append(unmatched)

    event.result_booking_ids = "|".join(item.booking_id for item in created_bookings)
    event.result_unmatched_booking_ids = "|".join(item.unmatched_booking_id for item in created_unmatched_bookings)
    event.updated_at = utcnow()

    if created_unmatched_bookings:
        event.processing_status = BookingEmailEventStatus.NEEDS_RESOLUTION
        event.notes = "One or more booking legs could not be matched confidently."
    elif created_bookings:
        event.processing_status = BookingEmailEventStatus.RESOLVED_AUTO
        if duplicate_count:
            event.notes = f"Created {len(created_bookings)} booking(s); skipped {duplicate_count} duplicate leg(s)."
        else:
            event.notes = "Created booking automatically from Gmail."
    else:
        event.processing_status = BookingEmailEventStatus.DUPLICATE
        event.notes = "All extracted legs already exist in the booking ledger."

    repository.append_booking_email_events([event])
    return BookingEmailProcessResult(
        event=event,
        created_bookings=created_bookings,
        created_unmatched_bookings=created_unmatched_bookings,
    )


def _message_search_text(message: GmailMessage) -> str:
    return "\n".join(
        [
            message.subject,
            message.body_text,
        ]
    ).lower()


def _looks_like_non_booking(text: str, config: GmailIntegrationConfig) -> bool:
    booking_hit = any(keyword.lower() in text for keyword in config.booking_keywords)
    spam_hit = any(keyword.lower() in text for keyword in config.spam_keywords)
    return spam_hit and not booking_hit


def _non_booking_reason(extraction: BookingEmailExtraction) -> str:
    if extraction.email_kind == "not_booking":
        return "Ignored after model classification: not a booking confirmation."
    if extraction.email_kind in {"itinerary_change", "cancellation"}:
        return f"Ignored for now: {extraction.email_kind.replace('_', ' ')} handling is not implemented yet."
    return "Ignored after model classification."


def _candidates_from_extraction(extraction: BookingEmailExtraction) -> list[BookingCandidate]:
    candidates: list[BookingCandidate] = []
    multi_leg_total_price = extraction.total_price if len(extraction.legs) > 1 else None
    for leg in extraction.legs:
        if leg.leg_status == "cancelled":
            continue
        if not (leg.airline and leg.origin_airport and leg.destination_airport and leg.departure_date and leg.departure_time):
            continue
        try:
            departure_date = date.fromisoformat(leg.departure_date)
        except ValueError:
            continue
        price = extraction.total_price or 0
        notes = "Imported from Gmail."
        if multi_leg_total_price is not None:
            price = 0
            notes = f"Imported from Gmail. Total itinerary price was ${multi_leg_total_price}."
        if extraction.record_locator:
            notes = f"{notes} Record locator {extraction.record_locator}."
        airline = _normalize_airline_code(leg.airline)
        candidates.append(
            BookingCandidate(
                airline=airline,
                origin_airport=leg.origin_airport,
                destination_airport=leg.destination_airport,
                departure_date=departure_date,
                departure_time=leg.departure_time,
                arrival_time=leg.arrival_time,
                booked_price=price,
                record_locator=extraction.record_locator,
                notes=notes,
            )
        )
    return candidates


def _normalize_airline_code(value: str) -> str:
    return normalize_airline_code(value)


def _booking_candidate_exists(repository: Repository, candidate: BookingCandidate) -> bool:
    for booking in repository.load_bookings():
        if _same_booking(booking, candidate):
            return True
    for unmatched in repository.load_unmatched_bookings():
        if (
            unmatched.airline == candidate.airline
            and unmatched.origin_airport == candidate.origin_airport
            and unmatched.destination_airport == candidate.destination_airport
            and unmatched.departure_date == candidate.departure_date
            and unmatched.departure_time == candidate.departure_time
            and unmatched.record_locator == candidate.record_locator
            and unmatched.resolution_status == "open"
        ):
            return True
    return False


def _same_booking(booking: Booking, candidate: BookingCandidate) -> bool:
    return (
        booking.airline == candidate.airline
        and booking.origin_airport == candidate.origin_airport
        and booking.destination_airport == candidate.destination_airport
        and booking.departure_date == candidate.departure_date
        and booking.departure_time == candidate.departure_time
        and booking.record_locator == candidate.record_locator
    )
