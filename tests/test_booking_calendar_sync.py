from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.models.base import BookingStatus
from app.models.booking import Booking
from app.services.booking_calendar_sync import sync_booking_calendar
from app.storage.repository import Repository


class _FakeRequest:
    def __init__(self, payload: dict[str, Any] | None = None):
        self.payload = payload or {}

    def execute(self):
        return self.payload


class _FakeCalendars:
    def __init__(self, service: "_FakeCalendarService"):
        self.service = service

    def get(self, *, calendarId: str):
        if calendarId not in self.service.calendars_by_id:
            raise AssertionError(f"Unexpected calendar lookup: {calendarId}")
        return _FakeRequest(self.service.calendars_by_id[calendarId])

    def insert(self, *, body: dict[str, Any]):
        calendar_id = f"calendar-{len(self.service.calendars_by_id) + 1}"
        payload = {"id": calendar_id, **body}
        self.service.calendars_by_id[calendar_id] = payload
        return _FakeRequest(payload)


class _FakeEvents:
    def __init__(self, service: "_FakeCalendarService"):
        self.service = service

    def insert(self, *, calendarId: str, body: dict[str, Any]):
        event_id = f"event-{len(self.service.events_by_id) + 1}"
        self.service.inserted.append(body)
        self.service.events_by_id[event_id] = {"id": event_id, **body}
        return _FakeRequest(self.service.events_by_id[event_id])

    def update(self, *, calendarId: str, eventId: str, body: dict[str, Any]):
        self.service.updated.append((eventId, body))
        self.service.events_by_id[eventId] = {"id": eventId, **body}
        return _FakeRequest(self.service.events_by_id[eventId])

    def delete(self, *, calendarId: str, eventId: str):
        self.service.deleted.append(eventId)
        self.service.events_by_id.pop(eventId, None)
        return _FakeRequest({})

    def list(self, *, calendarId: str, **_kwargs: Any):
        return _FakeRequest({"items": list(self.service.events_by_id.values())})


class _FakeCalendarService:
    def __init__(self):
        self.calendars_by_id: dict[str, dict[str, Any]] = {}
        self.events_by_id: dict[str, dict[str, Any]] = {}
        self.inserted: list[dict[str, Any]] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []
        self.deleted: list[str] = []

    def calendars(self):
        return _FakeCalendars(self)

    def events(self):
        return _FakeEvents(self)


def _booking(booking_id: str = "book_test") -> Booking:
    return Booking(
        booking_id=booking_id,
        source="manual",
        trip_instance_id="inst_test",
        airline="WN",
        origin_airport="SFO",
        destination_airport="BUR",
        departure_date=date(2026, 6, 10),
        departure_time="07:40",
        arrival_time="09:05",
        flight_number="4228",
        booked_price=Decimal("76.40"),
        record_locator="ABC123",
    )


def test_sync_booking_calendar_inserts_updates_and_deletes_events(repository: Repository) -> None:
    service = _FakeCalendarService()
    booking = _booking()
    repository.upsert_bookings([booking])

    first = sync_booking_calendar(repository, calendar_service=service)

    assert first.inserted_count == 1
    assert len(service.inserted) == 1
    assert service.inserted[0]["summary"] == "SFO to BUR · WN 4228"
    assert service.inserted[0]["extendedProperties"]["private"]["booking_id"] == booking.booking_id
    mapping = repository.load_booking_calendar_events()[0]
    assert mapping.calendar_event_id == "event-1"

    second = sync_booking_calendar(repository, calendar_service=service)

    assert second.skipped_count == 1
    assert service.updated == []

    booking.booked_price = Decimal("88.00")
    repository.upsert_bookings([booking])
    third = sync_booking_calendar(repository, calendar_service=service)

    assert third.updated_count == 1
    assert service.updated[0][0] == "event-1"
    assert "Booked price: $88" in service.updated[0][1]["description"]

    booking.status = BookingStatus.CANCELLED
    repository.upsert_bookings([booking])
    fourth = sync_booking_calendar(repository, calendar_service=service)

    assert fourth.deleted_count == 1
    assert service.deleted == ["event-1"]
    assert repository.load_booking_calendar_events() == []


def test_sync_booking_calendar_deletes_mapping_for_deleted_booking(repository: Repository) -> None:
    service = _FakeCalendarService()
    booking = _booking()
    repository.upsert_bookings([booking])
    sync_booking_calendar(repository, calendar_service=service)

    repository.delete_bookings_by_ids([booking.booking_id])
    result = sync_booking_calendar(repository, calendar_service=service)

    assert result.deleted_count == 1
    assert service.deleted == ["event-1"]
    assert repository.load_booking_calendar_events() == []


def test_sync_booking_calendar_can_force_verify_existing_events(repository: Repository) -> None:
    service = _FakeCalendarService()
    booking = _booking()
    repository.upsert_bookings([booking])
    sync_booking_calendar(repository, calendar_service=service)
    service.events_by_id["event-1"]["summary"] = "External edit"

    result = sync_booking_calendar(repository, calendar_service=service, verify_remote=True)

    assert result.updated_count == 1
    assert service.updated[0][0] == "event-1"
    assert service.updated[0][1]["summary"] == "SFO to BUR · WN 4228"
    assert service.events_by_id["event-1"]["summary"] == "SFO to BUR · WN 4228"


def test_sync_booking_calendar_verify_skips_matching_remote_events(repository: Repository) -> None:
    service = _FakeCalendarService()
    booking = _booking()
    repository.upsert_bookings([booking])
    sync_booking_calendar(repository, calendar_service=service)

    result = sync_booking_calendar(repository, calendar_service=service, verify_remote=True)

    assert result.skipped_count == 1
    assert service.updated == []


def test_sync_booking_calendar_verify_deletes_unmapped_duplicate_remote_events(repository: Repository) -> None:
    service = _FakeCalendarService()
    booking = _booking()
    repository.upsert_bookings([booking])
    sync_booking_calendar(repository, calendar_service=service)
    duplicate = {"id": "event-extra", **service.events_by_id["event-1"]}
    duplicate["id"] = "event-extra"
    service.events_by_id["event-extra"] = duplicate

    result = sync_booking_calendar(repository, calendar_service=service, verify_remote=True)

    assert result.deleted_count == 1
    assert service.deleted == ["event-extra"]
    assert "event-extra" not in service.events_by_id


def test_sync_booking_calendar_verify_does_not_double_count_stale_mapped_events(repository: Repository) -> None:
    service = _FakeCalendarService()
    booking = _booking()
    repository.upsert_bookings([booking])
    sync_booking_calendar(repository, calendar_service=service)

    booking.status = BookingStatus.CANCELLED
    repository.upsert_bookings([booking])
    result = sync_booking_calendar(repository, calendar_service=service, verify_remote=True)

    assert result.deleted_count == 1
    assert service.deleted == ["event-1"]


def test_sync_booking_calendar_uses_airport_timezones(repository: Repository) -> None:
    service = _FakeCalendarService()
    booking = _booking()
    booking.origin_airport = "JFK"
    booking.destination_airport = "LAX"
    booking.departure_time = "15:50"
    booking.arrival_time = "19:10"
    repository.upsert_bookings([booking])

    sync_booking_calendar(repository, calendar_service=service)

    assert service.inserted[0]["start"]["timeZone"] == "America/New_York"
    assert service.inserted[0]["end"]["timeZone"] == "America/Los_Angeles"
