from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from googleapiclient.errors import HttpError

from app.catalog import airport_time_zone, stop_display_label
from app.models.base import BookingMatchStatus, BookingStatus, DataScope, fare_class_label, utcnow
from app.models.booking import Booking
from app.models.booking_calendar_event import BookingCalendarEvent
from app.money import format_money
from app.services.calendar_sync_state import load_calendar_sync_state, save_calendar_sync_state
from app.services.gmail_client import GmailAuthorizationRequired, build_calendar_service
from app.settings import Settings
from app.storage.repository import Repository

logger = logging.getLogger(__name__)

CALENDAR_SUMMARY = "Flights"


class CalendarSyncError(RuntimeError):
    pass


class CalendarApi(Protocol):
    def calendars(self) -> Any:
        ...

    def events(self) -> Any:
        ...


@dataclass
class BookingCalendarSyncResult:
    disabled: bool = False
    calendar_id: str = ""
    inserted_count: int = 0
    updated_count: int = 0
    deleted_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)


def sync_booking_calendar_best_effort(repository: Repository) -> BookingCalendarSyncResult:
    try:
        return sync_booking_calendar(repository)
    except GmailAuthorizationRequired as exc:
        logger.info("Skipping booking calendar sync because Google authorization is unavailable: %s", exc)
        return BookingCalendarSyncResult(disabled=True, errors=[str(exc)])
    except Exception as exc:
        logger.exception("Booking calendar sync failed.")
        return BookingCalendarSyncResult(error_count=1, errors=[str(exc)])


def sync_booking_calendar(
    repository: Repository,
    *,
    calendar_service: CalendarApi | None = None,
    settings: Settings | None = None,
    verify_remote: bool = False,
) -> BookingCalendarSyncResult:
    settings = settings or repository.settings
    active_bookings = _active_live_bookings(repository)
    mappings = repository.load_booking_calendar_events()
    desired_by_id = {booking.booking_id: booking for booking in active_bookings}
    mapping_by_id = {mapping.booking_id: mapping for mapping in mappings}

    desired_hash_by_id = {
        booking_id: _event_hash(_event_body(booking, timezone=repository.load_app_state().timezone))
        for booking_id, booking in desired_by_id.items()
    }
    stale_mappings = [mapping for mapping in mappings if mapping.booking_id not in desired_by_id]
    changed_bookings = [
        booking
        for booking in active_bookings
        if mapping_by_id.get(booking.booking_id) is None
        or mapping_by_id[booking.booking_id].last_synced_hash != desired_hash_by_id[booking.booking_id]
        or mapping_by_id[booking.booking_id].last_error
    ]
    if not verify_remote and not stale_mappings and not changed_bookings:
        state = load_calendar_sync_state(settings)
        return BookingCalendarSyncResult(calendar_id=state.calendar_id, skipped_count=len(active_bookings))

    service = calendar_service or build_calendar_service(settings)
    calendar_id = _ensure_calendar(service, settings=settings)
    now = utcnow()
    result = BookingCalendarSyncResult(calendar_id=calendar_id)
    upserts: list[BookingCalendarEvent] = []
    deleted_booking_ids: list[str] = []
    if verify_remote:
        remote_events_by_id = _list_calendar_events_by_id(service, calendar_id=calendar_id)
        stale_event_ids = {mapping.calendar_event_id for mapping in stale_mappings if mapping.calendar_event_id}
        expected_event_ids_by_booking_id = {
            mapping.booking_id: mapping.calendar_event_id
            for mapping in mappings
            if mapping.booking_id in desired_by_id and mapping.calendar_event_id
        }
        for event in remote_events_by_id.values():
            event_id = str(event.get("id", "")).strip()
            private = (event.get("extendedProperties") or {}).get("private") or {}
            if private.get("app") != "milemark" or not event_id:
                continue
            if event_id in stale_event_ids:
                continue
            booking_id = str(private.get("booking_id", "")).strip()
            expected_event_id = expected_event_ids_by_booking_id.get(booking_id)
            if booking_id in desired_by_id and event_id == expected_event_id:
                continue
            try:
                _delete_event(service, calendar_id=calendar_id, event_id=event_id)
            except Exception as exc:
                result.errors.append(f"{booking_id or event_id}: {exc}")
                result.error_count += 1
                continue
            result.deleted_count += 1
        changed_booking_ids = {booking.booking_id for booking in changed_bookings}
        timezone = repository.load_app_state().timezone
        for booking in active_bookings:
            mapping = mapping_by_id.get(booking.booking_id)
            if mapping is None or booking.booking_id in changed_booking_ids:
                continue
            remote_event = remote_events_by_id.get(mapping.calendar_event_id)
            if remote_event is None or not _remote_event_matches_desired(
                remote_event,
                _event_body(booking, timezone=timezone),
            ):
                changed_bookings.append(booking)
                changed_booking_ids.add(booking.booking_id)
    if not stale_mappings and not changed_bookings:
        result.skipped_count = len(active_bookings)
        return result

    for mapping in stale_mappings:
        try:
            _delete_event(service, calendar_id=mapping.calendar_id or calendar_id, event_id=mapping.calendar_event_id)
        except Exception as exc:
            result.errors.append(f"{mapping.booking_id}: {exc}")
            result.error_count += 1
            mapping.last_error = str(exc)
            mapping.updated_at = now
            upserts.append(mapping)
            continue
        result.deleted_count += 1
        deleted_booking_ids.append(mapping.booking_id)

    timezone = repository.load_app_state().timezone
    for booking in changed_bookings:
        body = _event_body(booking, timezone=timezone)
        body_hash = _event_hash(body)
        existing_mapping = mapping_by_id.get(booking.booking_id)
        try:
            event_id = _upsert_event(
                service,
                calendar_id=calendar_id,
                event_id=existing_mapping.calendar_event_id if existing_mapping else "",
                body=body,
            )
        except Exception as exc:
            result.errors.append(f"{booking.booking_id}: {exc}")
            result.error_count += 1
            upserts.append(
                BookingCalendarEvent(
                    booking_id=booking.booking_id,
                    data_scope=booking.data_scope,
                    calendar_id=existing_mapping.calendar_id if existing_mapping else calendar_id,
                    calendar_event_id=existing_mapping.calendar_event_id if existing_mapping else "",
                    last_synced_hash=existing_mapping.last_synced_hash if existing_mapping else "",
                    last_synced_at=existing_mapping.last_synced_at if existing_mapping else None,
                    last_error=str(exc),
                    created_at=existing_mapping.created_at if existing_mapping else now,
                    updated_at=now,
                )
            )
            continue
        result.updated_count += 1 if existing_mapping else 0
        result.inserted_count += 0 if existing_mapping else 1
        upserts.append(
            BookingCalendarEvent(
                booking_id=booking.booking_id,
                data_scope=booking.data_scope,
                calendar_id=calendar_id,
                calendar_event_id=event_id,
                last_synced_hash=body_hash,
                last_synced_at=now,
                last_error="",
                created_at=existing_mapping.created_at if existing_mapping else now,
                updated_at=now,
            )
        )

    with repository.transaction():
        repository.upsert_booking_calendar_events(upserts)
        repository.delete_booking_calendar_events_by_booking_ids(deleted_booking_ids)
    return result


def _active_live_bookings(repository: Repository) -> list[Booking]:
    bookings = [
        booking
        for booking in [*repository.load_bookings(), *repository.load_unmatched_bookings()]
        if booking.status == BookingStatus.ACTIVE and str(booking.data_scope) == str(DataScope.LIVE)
    ]
    return sorted(
        bookings,
        key=lambda booking: (booking.departure_date, booking.departure_time, booking.booking_id),
    )


def _ensure_calendar(service: CalendarApi, *, settings: Settings) -> str:
    state = load_calendar_sync_state(settings)
    if state.calendar_id:
        try:
            service.calendars().get(calendarId=state.calendar_id).execute()
            return state.calendar_id
        except HttpError as exc:
            if _http_status(exc) not in {404, 410}:
                raise

    calendar = service.calendars().insert(
        body={
            "summary": state.calendar_summary or CALENDAR_SUMMARY,
            "timeZone": "America/Los_Angeles",
        }
    ).execute()
    calendar_id = str(calendar.get("id", "")).strip()
    if not calendar_id:
        raise CalendarSyncError("Google Calendar did not return a calendar id.")
    state.calendar_id = calendar_id
    state.calendar_summary = state.calendar_summary or CALENDAR_SUMMARY
    save_calendar_sync_state(settings, state)
    return calendar_id


def _event_body(booking: Booking, *, timezone: str) -> dict[str, Any]:
    start_at = _booking_start_datetime(booking)
    end_at = _booking_end_datetime(booking, start_at=start_at)
    start_time_zone = airport_time_zone(booking.origin_airport, fallback=timezone)
    end_time_zone = airport_time_zone(booking.destination_airport, fallback=timezone)
    private_properties = {
        "app": "milemark",
        "booking_id": booking.booking_id,
        "record_locator": booking.record_locator,
    }
    return {
        "summary": _event_summary(booking),
        "location": f"{booking.origin_airport} to {booking.destination_airport}",
        "description": _event_description(booking),
        "start": {
            "dateTime": start_at.isoformat(timespec="seconds"),
            "timeZone": start_time_zone,
        },
        "end": {
            "dateTime": end_at.isoformat(timespec="seconds"),
            "timeZone": end_time_zone,
        },
        "extendedProperties": {
            "private": private_properties,
        },
    }


def _event_summary(booking: Booking) -> str:
    flight_number = booking.flight_number.strip()
    route = f"{booking.origin_airport} to {booking.destination_airport}"
    return f"{route} · {flight_number}" if flight_number else route


def _event_description(booking: Booking) -> str:
    lines = [
        "Synced from Milemark.",
        f"Booking ID: {booking.booking_id}",
        f"Airline: {booking.airline}",
        f"Route: {booking.origin_airport} to {booking.destination_airport}",
        f"Departure: {booking.departure_date.isoformat()} {booking.departure_time}",
    ]
    if booking.arrival_time:
        arrival_date = booking.departure_date + timedelta(days=booking.arrival_day_offset)
        lines.append(f"Arrival: {arrival_date.isoformat()} {booking.arrival_time}")
    if booking.flight_number:
        lines.append(f"Flight number: {booking.flight_number}")
    if booking.record_locator:
        lines.append(f"Record locator: {booking.record_locator}")
    lines.extend(
        [
            f"Fare: {fare_class_label(booking.fare_class)}",
            f"Stops: {stop_display_label(booking.stops or 'nonstop')}",
            f"Booked price: {format_money(booking.booked_price)}",
        ]
    )
    if booking.match_status == BookingMatchStatus.UNMATCHED:
        lines.append("Status: Needs linking")
    if booking.notes:
        lines.extend(["", "Notes:", booking.notes])
    return "\n".join(lines)


def _booking_start_datetime(booking: Booking) -> datetime:
    return datetime.combine(booking.departure_date, _parse_time(booking.departure_time))


def _booking_end_datetime(booking: Booking, *, start_at: datetime) -> datetime:
    if not booking.arrival_time:
        return start_at + timedelta(hours=1)
    arrival_date = booking.departure_date + timedelta(days=booking.arrival_day_offset)
    end_at = datetime.combine(arrival_date, _parse_time(booking.arrival_time))
    if end_at <= start_at:
        return start_at + timedelta(hours=1)
    return end_at


def _parse_time(value: str) -> time:
    parsed = datetime.strptime(value, "%H:%M")
    return time(hour=parsed.hour, minute=parsed.minute)


def _event_hash(body: dict[str, Any]) -> str:
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _upsert_event(service: CalendarApi, *, calendar_id: str, event_id: str, body: dict[str, Any]) -> str:
    if event_id:
        try:
            event = service.events().update(calendarId=calendar_id, eventId=event_id, body=body).execute()
            return str(event.get("id", event_id))
        except HttpError as exc:
            if _http_status(exc) not in {404, 410}:
                raise
    event = service.events().insert(calendarId=calendar_id, body=body).execute()
    created_event_id = str(event.get("id", "")).strip()
    if not created_event_id:
        raise CalendarSyncError("Google Calendar did not return an event id.")
    return created_event_id


def _delete_event(service: CalendarApi, *, calendar_id: str, event_id: str) -> None:
    if not event_id:
        return
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    except HttpError as exc:
        if _http_status(exc) not in {404, 410}:
            raise


def _list_calendar_events_by_id(service: CalendarApi, *, calendar_id: str) -> dict[str, dict[str, Any]]:
    events_by_id: dict[str, dict[str, Any]] = {}
    page_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "calendarId": calendar_id,
            "maxResults": 2500,
            "showDeleted": False,
            "singleEvents": False,
        }
        if page_token:
            kwargs["pageToken"] = page_token
        payload = service.events().list(**kwargs).execute()
        for event in payload.get("items", []):
            event_id = str(event.get("id", "")).strip()
            if event_id:
                events_by_id[event_id] = event
        page_token = payload.get("nextPageToken")
        if not page_token:
            return events_by_id


def _remote_event_matches_desired(remote_event: dict[str, Any], desired_body: dict[str, Any]) -> bool:
    if remote_event.get("summary") != desired_body.get("summary"):
        return False
    if remote_event.get("location") != desired_body.get("location"):
        return False
    if remote_event.get("description") != desired_body.get("description"):
        return False
    if not _remote_endpoint_matches_desired(remote_event.get("start"), desired_body.get("start")):
        return False
    if not _remote_endpoint_matches_desired(remote_event.get("end"), desired_body.get("end")):
        return False
    remote_private = (remote_event.get("extendedProperties") or {}).get("private") or {}
    desired_private = (desired_body.get("extendedProperties") or {}).get("private") or {}
    return all(str(remote_private.get(key, "")) == str(value) for key, value in desired_private.items())


def _remote_endpoint_matches_desired(remote_endpoint: object, desired_endpoint: object) -> bool:
    if not isinstance(remote_endpoint, dict) or not isinstance(desired_endpoint, dict):
        return False
    if remote_endpoint.get("timeZone") != desired_endpoint.get("timeZone"):
        return False
    remote_datetime = _parse_google_datetime(
        remote_endpoint.get("dateTime"),
        timezone_name=str(remote_endpoint.get("timeZone") or ""),
    )
    desired_datetime = _desired_endpoint_datetime(desired_endpoint)
    if remote_datetime is None or desired_datetime is None:
        return False
    delta_seconds = abs((remote_datetime.astimezone(UTC) - desired_datetime.astimezone(UTC)).total_seconds())
    return delta_seconds < 60


def _parse_google_datetime(value: object, *, timezone_name: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed
        return parsed.replace(tzinfo=ZoneInfo(timezone_name))
    except (ValueError, ZoneInfoNotFoundError):
        return None


def _desired_endpoint_datetime(endpoint: dict[str, Any]) -> datetime | None:
    raw_datetime = str(endpoint.get("dateTime") or "").strip()
    raw_timezone = str(endpoint.get("timeZone") or "").strip()
    if not raw_datetime or not raw_timezone:
        return None
    try:
        zone = ZoneInfo(raw_timezone)
        return datetime.fromisoformat(raw_datetime).replace(tzinfo=zone)
    except (ValueError, ZoneInfoNotFoundError):
        return None


def _http_status(exc: HttpError) -> int | None:
    return getattr(getattr(exc, "resp", None), "status", None)
