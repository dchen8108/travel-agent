from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
import json

from app.catalog import normalize_airline_code
from app.money import format_money
from app.models.base import BookingEmailEventStatus, BookingStatus, DataScope, utcnow
from app.models.booking import Booking
from app.models.booking_email_event import BookingEmailEvent
from app.models.gmail_integration import GmailIntegrationConfig
from app.models.unmatched_booking import UnmatchedBooking
from app.services.booking_extraction import BookingEmailExtraction, extract_booking_email, prepare_booking_email_body
from app.services.bookings import BookingCandidate, matching_trip_instance_ids_for_booking, record_booking
from app.services.data_scope import filter_items, include_test_data_for_processing
from app.services.gmail_client import GmailMessage
from app.services.ids import new_id
from app.storage.repository import Repository


@dataclass
class BookingEmailProcessResult:
    event: BookingEmailEvent
    created_bookings: list[Booking]
    created_unmatched_bookings: list[UnmatchedBooking]
    state_changed: bool = False
    debug_fields: dict[str, object] = field(default_factory=dict)


def process_gmail_booking_message(
    repository: Repository,
    *,
    message: GmailMessage,
    config: GmailIntegrationConfig,
) -> BookingEmailProcessResult:
    existing_event = repository.get_booking_email_event_by_message_id(message.gmail_message_id)
    if existing_event is not None and existing_event.processing_status != BookingEmailEventStatus.ERROR:
        return BookingEmailProcessResult(
            event=existing_event,
            created_bookings=[],
            created_unmatched_bookings=[],
            state_changed=False,
        )
    if existing_event is not None and not _event_should_retry(existing_event, config):
        return BookingEmailProcessResult(
            event=existing_event,
            created_bookings=[],
            created_unmatched_bookings=[],
            state_changed=False,
        )

    event = existing_event or BookingEmailEvent(
        email_event_id=new_id("mail"),
        gmail_message_id=message.gmail_message_id,
        data_scope=DataScope.LIVE,
        gmail_thread_id=message.gmail_thread_id,
        gmail_history_id=message.gmail_history_id,
        from_address=message.from_address,
        subject=message.subject,
        received_at=message.received_at,
    )
    event.gmail_thread_id = message.gmail_thread_id
    event.gmail_history_id = message.gmail_history_id
    event.from_address = message.from_address
    event.subject = message.subject
    event.received_at = message.received_at
    event.retryable = True
    debug_fields: dict[str, object] = {
        "message_body_chars": len(message.body_text),
        "gmail_history_id": message.gmail_history_id,
        "keyword_gate": "passed",
        "llm": {
            "model": config.model,
            "max_body_chars": config.max_body_chars,
        },
        "matching": {
            "auto_create_confidence_threshold": config.min_auto_create_confidence,
        },
    }
    lowered = _message_search_text(message)
    if _looks_like_non_booking(lowered, config):
        event.processing_status = BookingEmailEventStatus.IGNORED
        event.email_kind = "not_booking"
        event.notes = "Ignored by booking keyword gate."
        event.updated_at = utcnow()
        debug_fields["keyword_gate"] = "ignored"
        debug_fields["keyword_gate_reason"] = "spam_keywords_matched_without_booking_keywords"
        _upsert_booking_email_event(repository, event)
        return BookingEmailProcessResult(
            event=event,
            created_bookings=[],
            created_unmatched_bookings=[],
            state_changed=False,
            debug_fields=debug_fields,
        )

    prepared_body_text = prepare_booking_email_body(message.body_text, max_chars=config.max_body_chars)
    debug_fields["llm"] = {
        **debug_fields["llm"],
        "prepared_body_chars": len(prepared_body_text),
    }
    if config.debug_log_model_io:
        debug_fields["llm"]["prepared_body"] = prepared_body_text

    try:
        event.extraction_attempt_count += 1
        extraction = extract_booking_email(
            settings=repository.settings,
            model=config.model,
            from_address=message.from_address,
            subject=message.subject,
            body_text=message.body_text,
            max_body_chars=config.max_body_chars,
            prepared_body_text=prepared_body_text,
        )
    except Exception as exc:
        retryable = _is_retryable_extraction_error(exc)
        event.processing_status = BookingEmailEventStatus.ERROR
        event.email_kind = "unknown"
        event.retryable = retryable
        event.notes = f"Extraction failed: {type(exc).__name__}: {exc}"
        if not retryable:
            event.notes = f"{event.notes} This email will not be retried automatically."
        event.updated_at = utcnow()
        debug_fields["llm"] = {
            **debug_fields["llm"],
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        _upsert_booking_email_event(repository, event)
        return BookingEmailProcessResult(
            event=event,
            created_bookings=[],
            created_unmatched_bookings=[],
            state_changed=False,
            debug_fields=debug_fields,
        )

    event.email_kind = extraction.email_kind
    event.extraction_confidence = extraction.confidence
    event.retryable = True
    event.extracted_payload_json = extraction.model_dump_json(indent=2)
    debug_fields["llm"] = {
        **debug_fields["llm"],
        "parsed_leg_count": len(extraction.legs),
        "parsed_summary": extraction.summary,
    }
    if config.debug_log_model_io:
        debug_fields["llm"]["parsed_output"] = json.loads(event.extracted_payload_json)

    if extraction.email_kind != "booking_confirmation":
        if extraction.email_kind == "cancellation":
            if extraction.confidence < config.min_auto_create_confidence:
                event.processing_status = BookingEmailEventStatus.NEEDS_RESOLUTION
                event.notes = (
                    f"Cancellation extraction confidence {extraction.confidence:.2f} "
                    f"is below the auto-apply threshold {config.min_auto_create_confidence:.2f}."
                )
                event.updated_at = utcnow()
                debug_fields["matching"] = {
                    **debug_fields["matching"],
                    "auto_apply_allowed": False,
                    "candidate_count": len(extraction.legs),
                }
                _upsert_booking_email_event(repository, event)
                return BookingEmailProcessResult(
                    event=event,
                    created_bookings=[],
                    created_unmatched_bookings=[],
                    state_changed=False,
                    debug_fields=debug_fields,
                )
            cancelled_bookings = _apply_cancellation(repository, extraction)
            event.result_booking_ids = "|".join(item.booking_id for item in cancelled_bookings)
            event.processing_status = (
                BookingEmailEventStatus.RESOLVED_AUTO if cancelled_bookings else BookingEmailEventStatus.NEEDS_RESOLUTION
            )
            event.notes = (
                f"Marked {len(cancelled_bookings)} booking(s) cancelled from Gmail."
                if cancelled_bookings
                else "Cancellation email could not be matched automatically."
            )
            event.updated_at = utcnow()
            debug_fields["matching"] = {
                **debug_fields["matching"],
                "auto_apply_allowed": True,
                "cancelled_booking_ids": [item.booking_id for item in cancelled_bookings],
                "candidate_count": len(extraction.legs),
            }
            _upsert_booking_email_event(repository, event)
            return BookingEmailProcessResult(
                event=event,
                created_bookings=cancelled_bookings,
                created_unmatched_bookings=[],
                state_changed=bool(cancelled_bookings),
                debug_fields=debug_fields,
            )
        event.processing_status = BookingEmailEventStatus.IGNORED
        event.notes = _non_booking_reason(extraction)
        event.updated_at = utcnow()
        _upsert_booking_email_event(repository, event)
        return BookingEmailProcessResult(
            event=event,
            created_bookings=[],
            created_unmatched_bookings=[],
            state_changed=False,
            debug_fields=debug_fields,
        )

    candidates = _candidates_from_extraction(extraction)
    if not candidates:
        event.processing_status = BookingEmailEventStatus.ERROR
        event.notes = "The extractor did not return any valid booking legs."
        event.updated_at = utcnow()
        debug_fields["matching"] = {
            **debug_fields["matching"],
            "candidate_count": 0,
        }
        _upsert_booking_email_event(repository, event)
        return BookingEmailProcessResult(
            event=event,
            created_bookings=[],
            created_unmatched_bookings=[],
            state_changed=False,
            debug_fields=debug_fields,
        )

    created_bookings: list[Booking] = []
    created_unmatched_bookings: list[UnmatchedBooking] = []
    duplicate_count = 0
    auto_create_allowed = extraction.confidence >= config.min_auto_create_confidence
    candidate_summaries: list[dict[str, object]] = []
    for candidate in candidates:
        matching_trip_instance_ids = matching_trip_instance_ids_for_booking(
            repository,
            candidate,
            data_scope=DataScope.LIVE,
        )
        candidate_summaries.append(
            {
                "airline": candidate.airline,
                "origin_airport": candidate.origin_airport,
                "destination_airport": candidate.destination_airport,
                "departure_date": candidate.departure_date.isoformat(),
                "departure_time": candidate.departure_time,
                "arrival_time": candidate.arrival_time,
                "record_locator": candidate.record_locator,
                "matching_trip_instance_ids": matching_trip_instance_ids,
            }
        )
        if _booking_candidate_exists(repository, candidate):
            duplicate_count += 1
            continue
        booking, unmatched = record_booking(
            repository,
            candidate,
            source="gmail",
            auto_link=auto_create_allowed,
        )
        if booking is not None:
            created_bookings.append(booking)
        if unmatched is not None:
            created_unmatched_bookings.append(unmatched)

    event.result_booking_ids = "|".join(item.booking_id for item in created_bookings)
    event.result_unmatched_booking_ids = "|".join(item.unmatched_booking_id for item in created_unmatched_bookings)
    event.updated_at = utcnow()
    debug_fields["matching"] = {
        **debug_fields["matching"],
        "auto_create_allowed": auto_create_allowed,
        "candidate_count": len(candidates),
        "candidates": candidate_summaries,
        "duplicate_count": duplicate_count,
    }

    if created_unmatched_bookings:
        event.processing_status = BookingEmailEventStatus.NEEDS_RESOLUTION
        if not auto_create_allowed:
            event.notes = (
                f"Extraction confidence {extraction.confidence:.2f} is below the auto-create "
                f"threshold {config.min_auto_create_confidence:.2f}; created unmatched booking(s) for review."
            )
        else:
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

    _upsert_booking_email_event(repository, event)
    return BookingEmailProcessResult(
        event=event,
        created_bookings=created_bookings,
        created_unmatched_bookings=created_unmatched_bookings,
        state_changed=bool(created_bookings or created_unmatched_bookings),
        debug_fields=debug_fields,
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
    if extraction.email_kind == "itinerary_change":
        return "Ignored for now: itinerary change handling is not implemented yet."
    return "Ignored after model classification."


def _event_should_retry(event: BookingEmailEvent, config: GmailIntegrationConfig) -> bool:
    if event.processing_status != BookingEmailEventStatus.ERROR:
        return False
    if not event.retryable:
        return False
    return event.extraction_attempt_count < config.max_retry_attempts


def _is_retryable_extraction_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if (
        "request too large" in message
        or "input or output tokens must be reduced" in message
        or "maximum context length" in message
        or "context length" in message
    ):
        return False
    retryable_names = {
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "RateLimitError",
    }
    if type(exc).__name__ in retryable_names:
        return True
    return (
        "quota exceeded" in message
        or "insufficient_quota" in message
        or "rate limit" in message
    )


def _candidates_from_extraction(extraction: BookingEmailExtraction) -> list[BookingCandidate]:
    candidates: list[BookingCandidate] = []
    extracted_total_price = extraction.total_price_amount()
    multi_leg_total_price = extracted_total_price if len(extraction.legs) > 1 else None
    for leg in extraction.legs:
        if not (leg.airline and leg.origin_airport and leg.destination_airport and leg.departure_date and leg.departure_time):
            continue
        try:
            departure_date = date.fromisoformat(leg.departure_date)
        except ValueError:
            continue
        price = extracted_total_price or Decimal("0")
        notes = "Imported from Gmail."
        if multi_leg_total_price is not None:
            price = Decimal("0")
            notes = f"Imported from Gmail. Total itinerary price was {format_money(multi_leg_total_price)}."
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
    include_test_data = include_test_data_for_processing(repository.load_app_state())
    for booking in filter_items(repository.load_bookings(), include_test_data=include_test_data):
        if _same_booking(booking, candidate):
            return True
    for unmatched in filter_items(repository.load_unmatched_bookings(), include_test_data=include_test_data):
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


def _upsert_booking_email_event(repository: Repository, event: BookingEmailEvent) -> None:
    repository.upsert_booking_email_event(event)


def _apply_cancellation(repository: Repository, extraction: BookingEmailExtraction) -> list[Booking]:
    include_test_data = include_test_data_for_processing(repository.load_app_state())
    bookings = filter_items(repository.load_bookings(), include_test_data=include_test_data)
    updated: list[Booking] = []
    matched_ids: set[str] = set()
    if not extraction.legs and extraction.record_locator:
        for booking in bookings:
            if booking.status == BookingStatus.CANCELLED:
                continue
            if booking.record_locator != extraction.record_locator:
                continue
            booking.status = BookingStatus.CANCELLED
            booking.updated_at = utcnow()
            updated.append(booking)
        if updated:
            repository.upsert_bookings(updated)
        return updated
    for leg in extraction.legs:
        if not (leg.departure_date or extraction.record_locator):
            continue
        departure_date: date | None = None
        if leg.departure_date:
            try:
                departure_date = date.fromisoformat(leg.departure_date)
            except ValueError:
                continue
        airline = _normalize_airline_code(leg.airline) if leg.airline else ""
        exact_matches: list[Booking] = []
        for booking in bookings:
            if booking.booking_id in matched_ids:
                continue
            if booking.status == BookingStatus.CANCELLED:
                continue
            locator_matches = bool(extraction.record_locator) and booking.record_locator == extraction.record_locator
            route_matches = (
                airline
                and booking.airline == airline
                and booking.origin_airport == leg.origin_airport
                and booking.destination_airport == leg.destination_airport
                and departure_date is not None
                and booking.departure_date == departure_date
                and (not leg.departure_time or booking.departure_time == leg.departure_time)
            )
            if locator_matches and route_matches:
                exact_matches.append(booking)

        target_bookings = exact_matches
        if not target_bookings and extraction.record_locator and len(extraction.legs) == 1:
            target_bookings = [
                booking
                for booking in bookings
                if booking.booking_id not in matched_ids
                and booking.status != BookingStatus.CANCELLED
                and booking.record_locator == extraction.record_locator
            ]
        if not target_bookings and departure_date is not None:
            target_bookings = [
                booking
                for booking in bookings
                if booking.booking_id not in matched_ids
                and booking.status != BookingStatus.CANCELLED
                and airline
                and booking.airline == airline
                and booking.origin_airport == leg.origin_airport
                and booking.destination_airport == leg.destination_airport
                and booking.departure_date == departure_date
                and (not leg.departure_time or booking.departure_time == leg.departure_time)
            ]

        for booking in target_bookings:
            booking.updated_at = utcnow()
            booking.status = BookingStatus.CANCELLED
            updated.append(booking)
            matched_ids.add(booking.booking_id)
    if updated:
        repository.upsert_bookings(updated)
    return updated


def loggable_debug_fields(
    debug_fields: dict[str, object],
    *,
    include_model_io: bool,
) -> dict[str, object]:
    if include_model_io:
        return debug_fields
    sanitized = dict(debug_fields)
    llm = dict(sanitized.get("llm") or {})
    llm.pop("prepared_body", None)
    llm.pop("parsed_output", None)
    sanitized["llm"] = llm
    return sanitized
