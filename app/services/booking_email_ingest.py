from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date, datetime, time, timedelta
from email.utils import parseaddr
import json

from app.catalog import normalize_airline_code, normalize_stop_value
from app.flight_numbers import join_flight_numbers
from app.money import format_money
from app.models.base import BookingEmailEventStatus, BookingStatus, DataScope, FareClass, parse_fare_class, utcnow
from app.models.booking import Booking
from app.models.booking_email_event import BookingEmailEvent
from app.models.gmail_integration import GmailIntegrationConfig
from app.services.booking_extraction import (
    BookingEmailExtraction,
    BookingEmailLeg,
    BookingEmailSegment,
    BookingExtractionError,
    extract_booking_email,
    prepare_booking_email_body,
)
from app.services.bookings import BookingCandidate, matching_trip_instance_ids_for_booking, record_booking
from app.services.data_scope import filter_items, include_test_data_for_processing
from app.services.gmail_client import GmailMessage
from app.services.ids import new_id
from app.storage.repository import Repository


@dataclass
class BookingEmailProcessResult:
    event: BookingEmailEvent
    created_bookings: list[Booking]
    created_unlinked_bookings: list[Booking]
    state_changed: bool = False
    debug_fields: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class _ResolvedLeg:
    leg: BookingEmailLeg
    departure_at: datetime
    arrival_at: datetime


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
            created_unlinked_bookings=[],
            state_changed=False,
        )
    if existing_event is not None and not _event_should_retry(existing_event, config):
        return BookingEmailProcessResult(
            event=existing_event,
            created_bookings=[],
            created_unlinked_bookings=[],
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
        "sender_gate": "passed",
        "keyword_gate": "passed",
        "llm": {
            "model": config.model,
            "max_body_chars": config.max_body_chars,
        },
        "matching": {
            "auto_create_confidence_threshold": config.min_auto_create_confidence,
        },
    }
    normalized_from_address = _normalized_from_address(message.from_address)
    if not _sender_allowed(message.from_address, config):
        event.processing_status = BookingEmailEventStatus.IGNORED
        event.email_kind = "not_booking"
        event.notes = f"Ignored because sender {normalized_from_address or 'unknown'} is not in allowed_from_addresses."
        event.updated_at = utcnow()
        debug_fields["sender_gate"] = "ignored"
        debug_fields["sender_gate_reason"] = "sender_not_allowlisted"
        _upsert_booking_email_event(repository, event)
        return BookingEmailProcessResult(
            event=event,
            created_bookings=[],
            created_unlinked_bookings=[],
            state_changed=False,
            debug_fields=debug_fields,
        )
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
            created_unlinked_bookings=[],
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
    except BookingExtractionError as exc:
        retryable = exc.retryable
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
            created_unlinked_bookings=[],
            state_changed=False,
            debug_fields=debug_fields,
        )

    event.email_kind = extraction.email_kind
    event.extraction_confidence = extraction.confidence
    event.retryable = True
    event.extracted_payload_json = extraction.model_dump_json(indent=2)
    debug_fields["llm"] = {
        **debug_fields["llm"],
        "parsed_segment_count": len(extraction.segments),
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
                    "candidate_count": len(_candidates_from_extraction(extraction)),
                }
                _upsert_booking_email_event(repository, event)
                return BookingEmailProcessResult(
                    event=event,
                    created_bookings=[],
                    created_unlinked_bookings=[],
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
                "candidate_count": len(_candidates_from_extraction(extraction)),
            }
            _upsert_booking_email_event(repository, event)
            return BookingEmailProcessResult(
                event=event,
                created_bookings=cancelled_bookings,
                created_unlinked_bookings=[],
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
            created_unlinked_bookings=[],
            state_changed=False,
            debug_fields=debug_fields,
        )

    candidates = _candidates_from_extraction(extraction)
    if not candidates:
        event.processing_status = BookingEmailEventStatus.ERROR
        event.notes = "The extractor did not return any valid booking segments."
        event.updated_at = utcnow()
        debug_fields["matching"] = {
            **debug_fields["matching"],
            "candidate_count": 0,
        }
        _upsert_booking_email_event(repository, event)
        return BookingEmailProcessResult(
            event=event,
            created_bookings=[],
            created_unlinked_bookings=[],
            state_changed=False,
            debug_fields=debug_fields,
        )

    created_bookings: list[Booking] = []
    created_unlinked_bookings: list[Booking] = []
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
                "arrival_day_offset": candidate.arrival_day_offset,
                "fare_class": candidate.fare_class,
                "stops": candidate.stops,
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
            created_unlinked_bookings.append(unmatched)

    event.result_booking_ids = "|".join(item.booking_id for item in created_bookings)
    event.result_unmatched_booking_ids = "|".join(item.unmatched_booking_id for item in created_unlinked_bookings)
    event.updated_at = utcnow()
    debug_fields["matching"] = {
        **debug_fields["matching"],
        "auto_create_allowed": auto_create_allowed,
        "candidate_count": len(candidates),
        "candidates": candidate_summaries,
        "duplicate_count": duplicate_count,
    }

    if created_unlinked_bookings:
        event.processing_status = BookingEmailEventStatus.NEEDS_RESOLUTION
        if not auto_create_allowed:
            event.notes = (
                f"Extraction confidence {extraction.confidence:.2f} is below the auto-create "
                f"threshold {config.min_auto_create_confidence:.2f}; created unlinked booking(s) for review."
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
        event.notes = "All extracted booking segments already exist in the booking ledger."

    _upsert_booking_email_event(repository, event)
    return BookingEmailProcessResult(
        event=event,
        created_bookings=created_bookings,
        created_unlinked_bookings=created_unlinked_bookings,
        state_changed=bool(created_bookings or created_unlinked_bookings),
        debug_fields=debug_fields,
    )


def _message_search_text(message: GmailMessage) -> str:
    return "\n".join(
        [
            message.subject,
            message.body_text,
        ]
    ).lower()


def _normalized_from_address(value: str) -> str:
    _name, address = parseaddr(value)
    return (address or value).strip().lower()


def _sender_allowed(message_from_address: str, config: GmailIntegrationConfig) -> bool:
    if not config.allowed_from_addresses:
        return True
    normalized = _normalized_from_address(message_from_address)
    return normalized in set(config.allowed_from_addresses)


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


def _candidates_from_extraction(extraction: BookingEmailExtraction) -> list[BookingCandidate]:
    segments = _segments_from_extraction(extraction)
    if not segments:
        return []

    candidates: list[BookingCandidate] = []
    extracted_total_price = extraction.effective_total_price_amount()
    multi_segment_total_price = extracted_total_price if len(segments) > 1 else None
    pricing_notes = _pricing_notes_from_extraction(extraction)
    for segment in segments:
        if not (
            segment.airline
            and segment.origin_airport
            and segment.destination_airport
            and segment.departure_date
            and segment.departure_time
        ):
            continue
        departure_date = _parse_iso_date(segment.departure_date)
        if departure_date is None:
            continue
        price = extracted_total_price or Decimal("0")
        notes = "Imported from Gmail."
        if multi_segment_total_price is not None:
            price = Decimal("0")
            notes = f"Imported from Gmail. Total itinerary value was {format_money(multi_segment_total_price)}."
        elif pricing_notes:
            notes = f"{notes} {pricing_notes}"
        if extraction.record_locator:
            notes = f"{notes} Record locator {extraction.record_locator}."
        elif pricing_notes and not multi_segment_total_price:
            notes = notes.strip()
        airline = _normalize_airline_code(segment.airline)
        candidates.append(
            BookingCandidate(
                airline=airline,
                origin_airport=segment.origin_airport,
                destination_airport=segment.destination_airport,
                departure_date=departure_date,
                departure_time=segment.departure_time,
                arrival_time=segment.arrival_time,
                arrival_day_offset=_arrival_day_offset_for_times(
                    segment.departure_time,
                    segment.arrival_time,
                    explicit_offset=segment.arrival_day_offset,
                ),
                stops=_normalized_segment_stops(segment.stops),
                flight_number=segment.flight_number,
                fare_class=_fare_class_from_extracted_value(segment.fare_class),
                booked_price=price,
                record_locator=extraction.record_locator,
                notes=notes,
            )
        )
    return candidates


def _normalize_airline_code(value: str) -> str:
    return normalize_airline_code(value)


def _pricing_notes_from_extraction(extraction: BookingEmailExtraction) -> str:
    parts: list[str] = []
    credits_amount = extraction.flight_credits_amount()
    if credits_amount is not None and credits_amount > Decimal("0"):
        parts.append(f"Included {format_money(credits_amount)} flight credit.")
    if extraction.points_used > 0:
        parts.append(
            f"Redeemed {extraction.points_used:,} points valued at {format_money(extraction.points_value_amount())}."
        )
    return " ".join(parts)


def _segments_from_extraction(extraction: BookingEmailExtraction) -> list[BookingEmailSegment]:
    explicit_segments = [segment for segment in extraction.segments if _segment_has_core_fields(segment)]
    if explicit_segments:
        inferred_segments = _segments_from_legs(extraction.legs)
        return [_enrich_explicit_segment(segment, inferred_segments) for segment in explicit_segments]
    return _segments_from_legs(extraction.legs)


def _segment_has_core_fields(segment: BookingEmailSegment) -> bool:
    return bool(
        segment.airline
        and segment.origin_airport
        and segment.destination_airport
        and segment.departure_date
        and segment.departure_time
    )


def _segments_from_legs(legs: list[BookingEmailLeg]) -> list[BookingEmailSegment]:
    resolved_legs = [resolved for leg in legs if (resolved := _resolve_leg(leg)) is not None]
    if not resolved_legs:
        return []
    segments: list[list[_ResolvedLeg]] = []
    current_segment: list[_ResolvedLeg] = []
    for resolved in resolved_legs:
        if current_segment and _legs_belong_to_same_segment(current_segment[-1], resolved):
            current_segment.append(resolved)
            continue
        if current_segment:
            segments.append(current_segment)
        current_segment = [resolved]
    if current_segment:
        segments.append(current_segment)
    return [_segment_from_resolved_legs(segment) for segment in segments]


def _resolve_leg(leg: BookingEmailLeg) -> _ResolvedLeg | None:
    if not (leg.airline and leg.origin_airport and leg.destination_airport and leg.departure_date and leg.departure_time):
        return None
    departure_date = _parse_iso_date(leg.departure_date)
    departure_time = _parse_hhmm(leg.departure_time)
    if departure_date is None or departure_time is None:
        return None
    departure_at = datetime.combine(departure_date, departure_time)
    arrival_time = _parse_hhmm(leg.arrival_time) or departure_time
    arrival_at = datetime.combine(departure_date, arrival_time) + timedelta(
        days=_arrival_day_offset_for_times(
            leg.departure_time,
            leg.arrival_time,
            explicit_offset=leg.arrival_day_offset,
        )
    )
    return _ResolvedLeg(leg=leg, departure_at=departure_at, arrival_at=arrival_at)


def _legs_belong_to_same_segment(previous: _ResolvedLeg, current: _ResolvedLeg) -> bool:
    if previous.leg.leg_status != current.leg.leg_status:
        return False
    if previous.leg.destination_airport != current.leg.origin_airport:
        return False
    layover = current.departure_at - previous.arrival_at
    return timedelta(0) <= layover <= timedelta(hours=12)


def _segment_from_resolved_legs(resolved_legs: list[_ResolvedLeg]) -> BookingEmailSegment:
    first = resolved_legs[0]
    last = resolved_legs[-1]
    flight_number = join_flight_numbers(leg.leg.flight_number for leg in resolved_legs)
    fare_class = _shared_leg_fare_class(resolved_legs)
    evidence = " | ".join(leg.leg.evidence for leg in resolved_legs if leg.leg.evidence)
    stops = _stop_value_for_connection_count(len(resolved_legs) - 1)
    arrival_day_offset = max(0, (last.arrival_at.date() - first.departure_at.date()).days)
    return BookingEmailSegment(
        airline=first.leg.airline,
        origin_airport=first.leg.origin_airport,
        destination_airport=last.leg.destination_airport,
        departure_date=first.leg.departure_date,
        departure_time=first.leg.departure_time,
        arrival_time=last.leg.arrival_time,
        arrival_day_offset=arrival_day_offset,
        stops=stops,
        flight_number=flight_number,
        segment_status=first.leg.leg_status,
        fare_class=fare_class,
        evidence=evidence,
    )


def _enrich_explicit_segment(
    segment: BookingEmailSegment,
    inferred_segments: list[BookingEmailSegment],
) -> BookingEmailSegment:
    matched = next(
        (
            inferred
            for inferred in inferred_segments
            if inferred.origin_airport == segment.origin_airport
            and inferred.destination_airport == segment.destination_airport
            and inferred.departure_date == segment.departure_date
            and inferred.departure_time == segment.departure_time
        ),
        None,
    )
    if matched is None:
        return segment

    fare_class = segment.fare_class
    if (fare_class or "").strip().lower() in {"", "unknown"} and (matched.fare_class or "").strip().lower() not in {"", "unknown"}:
        fare_class = matched.fare_class

    return segment.model_copy(
        update={
            "fare_class": fare_class,
            "flight_number": segment.flight_number or matched.flight_number,
            "stops": segment.stops or matched.stops,
        }
    )


def _shared_leg_fare_class(resolved_legs: list[_ResolvedLeg]) -> str:
    known_fares = [
        (leg.leg.fare_class or "").strip().lower()
        for leg in resolved_legs
        if (leg.leg.fare_class or "").strip().lower() not in {"", "unknown"}
    ]
    if not known_fares:
        return "unknown"
    first = known_fares[0]
    if all(fare == first for fare in known_fares):
        return first
    return "unknown"


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_hhmm(value: str) -> time | None:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def _stop_value_for_connection_count(count: int) -> str:
    if count <= 0:
        return "nonstop"
    if count == 1:
        return "1_stop"
    return "2_stops"


def _normalized_segment_stops(value: str) -> str:
    return normalize_stop_value(value, allow_empty=True)


def _arrival_day_offset_for_times(departure_time: str, arrival_time: str, *, explicit_offset: int = 0) -> int:
    if explicit_offset > 0:
        return explicit_offset
    if not departure_time or not arrival_time:
        return 0
    return 1 if arrival_time < departure_time else 0


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
            and unmatched.fare_class == candidate.fare_class
            and _stop_fields_match(unmatched.stops, candidate.stops)
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
        and booking.fare_class == candidate.fare_class
        and _stop_fields_match(booking.stops, candidate.stops)
        and booking.record_locator == candidate.record_locator
    )


def _stop_fields_match(existing: str | None, incoming: str | None) -> bool:
    normalized_existing = normalize_stop_value(existing, allow_empty=True)
    normalized_incoming = normalize_stop_value(incoming, allow_empty=True)
    if not normalized_existing or not normalized_incoming:
        return True
    return normalized_existing == normalized_incoming


def _fare_class_from_extracted_value(raw: str) -> FareClass:
    normalized = (raw or "").strip().lower()
    if normalized in {"", "unknown"}:
        return FareClass.BASIC_ECONOMY
    return parse_fare_class(normalized, default=FareClass.BASIC_ECONOMY)


def _upsert_booking_email_event(repository: Repository, event: BookingEmailEvent) -> None:
    repository.upsert_booking_email_event(event)


def _apply_cancellation(repository: Repository, extraction: BookingEmailExtraction) -> list[Booking]:
    include_test_data = include_test_data_for_processing(repository.load_app_state())
    bookings = filter_items(repository.load_bookings(), include_test_data=include_test_data)
    updated: list[Booking] = []
    matched_ids: set[str] = set()
    cancellation_candidates = _candidates_from_extraction(extraction)
    if not cancellation_candidates and extraction.record_locator:
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
    for candidate in cancellation_candidates:
        if not (candidate.departure_date or extraction.record_locator):
            continue
        departure_date = candidate.departure_date
        airline = candidate.airline
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
                and booking.origin_airport == candidate.origin_airport
                and booking.destination_airport == candidate.destination_airport
                and departure_date is not None
                and booking.departure_date == departure_date
                and (not candidate.departure_time or booking.departure_time == candidate.departure_time)
                and _stop_fields_match(booking.stops, candidate.stops)
            )
            if locator_matches and route_matches:
                exact_matches.append(booking)

        target_bookings = exact_matches
        if not target_bookings and extraction.record_locator and len(cancellation_candidates) == 1:
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
                and booking.origin_airport == candidate.origin_airport
                and booking.destination_airport == candidate.destination_airport
                and booking.departure_date == departure_date
                and (not candidate.departure_time or booking.departure_time == candidate.departure_time)
                and _stop_fields_match(booking.stops, candidate.stops)
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
