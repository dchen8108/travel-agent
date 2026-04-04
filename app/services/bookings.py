from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import date, datetime

from app.models.base import BookingMatchStatus, BookingStatus, DataScope, UnmatchedBookingStatus, utcnow
from app.models.booking import Booking
from app.models.tracker import Tracker
from app.route_options import time_in_window
from app.route_options import join_pipe, split_pipe
from app.services.data_scope import filter_items, include_test_data_for_processing
from app.services.ids import new_id
from app.storage.repository import Repository


@dataclass
class BookingCandidate:
    airline: str
    origin_airport: str
    destination_airport: str
    departure_date: date
    departure_time: str
    arrival_time: str
    booked_price: Decimal
    record_locator: str
    notes: str = ""


def _build_booking(
    candidate: BookingCandidate,
    *,
    source: str,
    trip_instance_id: str,
    route_option_id: str = "",
    data_scope: str,
    notes: str | None = None,
) -> Booking:
    return Booking(
        booking_id=new_id("book"),
        source=source,
        trip_instance_id=trip_instance_id,
        route_option_id=route_option_id,
        data_scope=DataScope(data_scope),
        airline=candidate.airline,
        origin_airport=candidate.origin_airport,
        destination_airport=candidate.destination_airport,
        departure_date=candidate.departure_date,
        departure_time=candidate.departure_time,
        arrival_time=candidate.arrival_time,
        booked_price=candidate.booked_price,
        record_locator=candidate.record_locator,
        notes=candidate.notes if notes is None else notes,
    )


def _save_booking(repository: Repository, booking: Booking) -> Booking:
    repository.upsert_bookings([booking])
    return booking


def _booking_to_unmatched(booking: Booking) -> Booking:
    return Booking(
        booking_id=booking.booking_id,
        source=booking.source,
        data_scope=booking.data_scope,
        trip_instance_id="",
        route_option_id="",
        airline=booking.airline,
        origin_airport=booking.origin_airport,
        destination_airport=booking.destination_airport,
        departure_date=booking.departure_date,
        departure_time=booking.departure_time,
        arrival_time=booking.arrival_time,
        booked_price=booking.booked_price,
        record_locator=booking.record_locator,
        raw_summary="",
        candidate_trip_instance_ids="",
        auto_link_enabled=False,
        booked_at=booking.booked_at,
        status=booking.status,
        match_status=BookingMatchStatus.UNMATCHED,
        resolution_status=UnmatchedBookingStatus.OPEN,
        notes=booking.notes,
        created_at=booking.created_at,
        updated_at=utcnow(),
    )


def _unlink_booking_record(repository: Repository, booking: Booking) -> Booking:
    replacement = _booking_to_unmatched(booking)
    with repository.transaction():
        repository.delete_bookings_by_ids([booking.booking_id])
        repository.delete_unmatched_bookings_by_ids([booking.booking_id])
        repository.upsert_unmatched_bookings([replacement])
    return replacement


def _matching_trackers_for_booking(candidate: BookingCandidate, trackers: list[Tracker]) -> list[Tracker]:
    matches: list[Tracker] = []
    for tracker in trackers:
        if tracker.travel_date != candidate.departure_date:
            continue
        if candidate.origin_airport not in tracker.origin_codes:
            continue
        if candidate.destination_airport not in tracker.destination_codes:
            continue
        if candidate.airline not in tracker.airline_codes:
            continue
        if not time_in_window(tracker.start_time, tracker.end_time, candidate.departure_time):
            continue
        matches.append(tracker)
    return matches


def _matching_trip_instance_ids_for_booking(candidate: BookingCandidate, trackers: list[Tracker]) -> list[str]:
    matching_trackers = _matching_trackers_for_booking(candidate, trackers)
    return sorted({tracker.trip_instance_id for tracker in matching_trackers})


def _matching_route_option_ids_for_booking(
    candidate: BookingCandidate,
    trackers: list[Tracker],
    *,
    trip_instance_id: str,
) -> list[str]:
    matching_trackers = [
        tracker
        for tracker in _matching_trackers_for_booking(candidate, trackers)
        if tracker.trip_instance_id == trip_instance_id
    ]
    return sorted({tracker.route_option_id for tracker in matching_trackers if tracker.route_option_id})


def _route_option_id_for_booking(
    candidate: BookingCandidate,
    trackers: list[Tracker],
    *,
    trip_instance_id: str,
) -> str:
    matching_route_option_ids = _matching_route_option_ids_for_booking(
        candidate,
        trackers,
        trip_instance_id=trip_instance_id,
    )
    if len(matching_route_option_ids) == 1:
        return matching_route_option_ids[0]
    return ""


def matching_trip_instance_ids_for_booking(
    repository: Repository,
    candidate: BookingCandidate,
    *,
    data_scope: str = DataScope.LIVE,
) -> list[str]:
    include_test_data = include_test_data_for_processing(repository.load_app_state()) or str(data_scope) == DataScope.TEST
    trackers = filter_items(repository.load_trackers(), include_test_data=include_test_data)
    return _matching_trip_instance_ids_for_booking(candidate, trackers)


def _candidate_from_unmatched(unmatched: Booking) -> BookingCandidate:
    return BookingCandidate(
        airline=unmatched.airline,
        origin_airport=unmatched.origin_airport,
        destination_airport=unmatched.destination_airport,
        departure_date=unmatched.departure_date,
        departure_time=unmatched.departure_time,
        arrival_time=unmatched.arrival_time,
        booked_price=unmatched.booked_price,
        record_locator=unmatched.record_locator,
    )


def _candidate_from_booking(booking: Booking) -> BookingCandidate:
    return BookingCandidate(
        airline=booking.airline,
        origin_airport=booking.origin_airport,
        destination_airport=booking.destination_airport,
        departure_date=booking.departure_date,
        departure_time=booking.departure_time,
        arrival_time=booking.arrival_time,
        booked_price=booking.booked_price,
        record_locator=booking.record_locator,
        notes=booking.notes,
    )


def suggested_route_option_payload_for_booking(candidate: BookingCandidate) -> dict[str, object]:
    departure = datetime.strptime(candidate.departure_time, "%H:%M")
    departure_minutes = departure.hour * 60 + departure.minute
    start_minutes = max(0, departure_minutes - 60)
    end_minutes = min((23 * 60) + 59, departure_minutes + 120)
    start_time = f"{start_minutes // 60:02d}:{start_minutes % 60:02d}"
    end_time = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"
    return {
        "origin_airports": candidate.origin_airport,
        "destination_airports": candidate.destination_airport,
        "airlines": candidate.airline,
        "day_offset": 0,
        "start_time": start_time,
        "end_time": end_time,
    }


def reconcile_booking_route_options(
    *,
    bookings: list[Booking],
    trackers: list[Tracker],
) -> list[Booking]:
    for booking in bookings:
        next_route_option_id = _route_option_id_for_booking(
            _candidate_from_booking(booking),
            trackers,
            trip_instance_id=booking.trip_instance_id,
        )
        if booking.route_option_id == next_route_option_id:
            continue
        booking.route_option_id = next_route_option_id
        booking.updated_at = utcnow()
    return bookings


def reconcile_unmatched_bookings(
    *,
    bookings: list[Booking],
    unmatched_bookings: list[Booking],
    trip_instances: list,
    trackers: list[Tracker],
) -> tuple[list[Booking], list[Booking]]:
    trip_instances_by_id = {item.trip_instance_id: item for item in trip_instances}
    remaining_unmatched: list[Booking] = []
    for unmatched in unmatched_bookings:
        valid_candidate_ids = {
            item for item in split_pipe(unmatched.candidate_trip_instance_ids) if item in trip_instances_by_id
        }
        if unmatched.resolution_status != UnmatchedBookingStatus.OPEN:
            unmatched.candidate_trip_instance_ids = join_pipe(sorted(valid_candidate_ids))
            remaining_unmatched.append(unmatched)
            continue

        candidate = _candidate_from_unmatched(unmatched)
        matching_trip_instance_ids = _matching_trip_instance_ids_for_booking(candidate, trackers)
        unmatched.candidate_trip_instance_ids = join_pipe(matching_trip_instance_ids)
        unmatched.updated_at = utcnow()

        if not unmatched.auto_link_enabled:
            remaining_unmatched.append(unmatched)
            continue
        if len(matching_trip_instance_ids) != 1:
            remaining_unmatched.append(unmatched)
            continue

        matched_trip_instance = trip_instances_by_id.get(matching_trip_instance_ids[0])
        if matched_trip_instance is None:
            remaining_unmatched.append(unmatched)
            continue
        if any(
            booking.trip_instance_id == matched_trip_instance.trip_instance_id
            and booking.airline == candidate.airline
            and booking.origin_airport == candidate.origin_airport
            and booking.destination_airport == candidate.destination_airport
            and booking.departure_date == candidate.departure_date
            and booking.departure_time == candidate.departure_time
            and booking.record_locator == candidate.record_locator
            for booking in bookings
        ):
            unmatched.match_status = BookingMatchStatus.MATCHED
            unmatched.trip_instance_id = matched_trip_instance.trip_instance_id
            unmatched.route_option_id = _route_option_id_for_booking(
                candidate,
                trackers,
                trip_instance_id=matched_trip_instance.trip_instance_id,
            )
            unmatched.resolution_status = UnmatchedBookingStatus.RESOLVED
            continue

        notes = "Automatically linked after a matching trip became available."
        bookings.append(
            Booking(
                booking_id=unmatched.booking_id,
                source=unmatched.source,
                trip_instance_id=matched_trip_instance.trip_instance_id,
                route_option_id=_route_option_id_for_booking(
                    candidate,
                    trackers,
                    trip_instance_id=matched_trip_instance.trip_instance_id,
                ),
                data_scope=matched_trip_instance.data_scope,
                airline=candidate.airline,
                origin_airport=candidate.origin_airport,
                destination_airport=candidate.destination_airport,
                departure_date=candidate.departure_date,
                departure_time=candidate.departure_time,
                arrival_time=candidate.arrival_time,
                booked_price=candidate.booked_price,
                record_locator=candidate.record_locator,
                booked_at=unmatched.booked_at,
                status=unmatched.status,
                match_status=BookingMatchStatus.MATCHED,
                raw_summary="",
                candidate_trip_instance_ids=join_pipe(matching_trip_instance_ids),
                auto_link_enabled=unmatched.auto_link_enabled,
                resolution_status=UnmatchedBookingStatus.RESOLVED,
                notes=notes,
                created_at=unmatched.created_at,
                updated_at=utcnow(),
            )
        )
    return bookings, remaining_unmatched


def record_booking(
    repository: Repository,
    candidate: BookingCandidate,
    *,
    trip_instance_id: str = "",
    source: str = "manual",
    data_scope: str = DataScope.LIVE,
    auto_link: bool = True,
) -> tuple[Booking | None, Booking | None]:
    app_state = repository.load_app_state()
    include_test_data = include_test_data_for_processing(app_state) or str(data_scope) == DataScope.TEST
    trip_instances = filter_items(repository.load_trip_instances(), include_test_data=include_test_data)
    trackers = filter_items(repository.load_trackers(), include_test_data=include_test_data)

    selected_trip = next((item for item in trip_instances if item.trip_instance_id == trip_instance_id), None) if trip_instance_id else None

    if selected_trip:
        booking = _build_booking(
            candidate,
            source=source,
            trip_instance_id=selected_trip.trip_instance_id,
            route_option_id=_route_option_id_for_booking(
                candidate,
                trackers,
                trip_instance_id=selected_trip.trip_instance_id,
            ),
            data_scope=selected_trip.data_scope,
        )
        return _save_booking(repository, booking), None

    matching_trip_instance_ids = _matching_trip_instance_ids_for_booking(candidate, trackers)
    if auto_link and len(matching_trip_instance_ids) == 1:
        matched_trip_instance_id = matching_trip_instance_ids[0]
        matched_trip_instance = next(
            item for item in trip_instances if item.trip_instance_id == matched_trip_instance_id
        )
        booking = _build_booking(
            candidate,
            source=source,
            trip_instance_id=matched_trip_instance.trip_instance_id,
            route_option_id=_route_option_id_for_booking(
                candidate,
                trackers,
                trip_instance_id=matched_trip_instance.trip_instance_id,
            ),
            data_scope=matched_trip_instance.data_scope,
        )
        return _save_booking(repository, booking), None

    unmatched = Booking(
        booking_id=new_id("ub"),
        source=source,
        trip_instance_id="",
        route_option_id="",
        data_scope=DataScope(data_scope),
        airline=candidate.airline,
        origin_airport=candidate.origin_airport,
        destination_airport=candidate.destination_airport,
        departure_date=candidate.departure_date,
        departure_time=candidate.departure_time,
        arrival_time=candidate.arrival_time,
        booked_price=candidate.booked_price,
        record_locator=candidate.record_locator,
        booked_at=utcnow(),
        status=BookingStatus.ACTIVE,
        match_status=BookingMatchStatus.UNMATCHED,
        raw_summary=f"{candidate.airline} {candidate.origin_airport}->{candidate.destination_airport} {candidate.departure_date.isoformat()} {candidate.departure_time}",
        candidate_trip_instance_ids="|".join(
            matching_trip_instance_ids
        ),
        auto_link_enabled=auto_link,
        resolution_status=UnmatchedBookingStatus.OPEN,
    )
    repository.upsert_unmatched_bookings([unmatched])
    return None, unmatched


def resolve_unmatched_booking_to_trip_instance(
    repository: Repository,
    *,
    unmatched_booking_id: str,
    trip_instance_id: str,
) -> Booking:
    unmatched_bookings = repository.load_unmatched_bookings()
    unmatched = next((item for item in unmatched_bookings if item.unmatched_booking_id == unmatched_booking_id), None)
    if unmatched is None:
        existing = next((item for item in repository.load_bookings() if item.booking_id == unmatched_booking_id), None)
        if existing is not None and existing.trip_instance_id == trip_instance_id:
            return existing
        raise KeyError("Unmatched booking not found")
    if unmatched.resolution_status != UnmatchedBookingStatus.OPEN:
        existing = next((item for item in repository.load_bookings() if item.booking_id == unmatched_booking_id), None)
        if existing is not None and existing.trip_instance_id == trip_instance_id:
            return existing
        raise KeyError("Unmatched booking not found")

    candidate = BookingCandidate(
        airline=unmatched.airline,
        origin_airport=unmatched.origin_airport,
        destination_airport=unmatched.destination_airport,
        departure_date=unmatched.departure_date,
        departure_time=unmatched.departure_time,
        arrival_time=unmatched.arrival_time,
        booked_price=unmatched.booked_price,
        record_locator=unmatched.record_locator,
    )

    booking = Booking(
        booking_id=unmatched.booking_id,
        source=unmatched.source,
        trip_instance_id=trip_instance_id,
        route_option_id=_route_option_id_for_booking(
            candidate,
            repository.load_trackers(),
            trip_instance_id=trip_instance_id,
        ),
        data_scope=unmatched.data_scope,
        airline=candidate.airline,
        origin_airport=candidate.origin_airport,
        destination_airport=candidate.destination_airport,
        departure_date=candidate.departure_date,
        departure_time=candidate.departure_time,
        arrival_time=candidate.arrival_time,
        booked_price=candidate.booked_price,
        record_locator=candidate.record_locator,
        booked_at=unmatched.booked_at,
        status=unmatched.status,
        match_status=BookingMatchStatus.MATCHED,
        raw_summary="",
        candidate_trip_instance_ids=unmatched.candidate_trip_instance_ids,
        auto_link_enabled=unmatched.auto_link_enabled,
        resolution_status=UnmatchedBookingStatus.RESOLVED,
        notes="Resolved from unmatched booking",
        created_at=unmatched.created_at,
        updated_at=utcnow(),
    )
    with repository.transaction():
        _save_booking(repository, booking)
        repository.delete_unmatched_bookings_by_ids([unmatched.booking_id])
    return booking


def resolve_unmatched_booking_to_trip(
    repository: Repository,
    *,
    unmatched_booking_id: str,
    trip_id: str,
) -> Booking | None:
    unmatched_bookings = repository.load_unmatched_bookings()
    unmatched = next((item for item in unmatched_bookings if item.unmatched_booking_id == unmatched_booking_id), None)
    trip_instance_ids = {
        item.trip_instance_id
        for item in repository.load_trip_instances()
        if item.trip_id == trip_id and not item.deleted
    }
    if unmatched is None:
        existing = next(
            (
                item
                for item in repository.load_bookings()
                if item.booking_id == unmatched_booking_id and item.trip_instance_id in trip_instance_ids
            ),
            None,
        )
        if existing is not None:
            return existing
        raise KeyError("Unmatched booking not found")
    candidate = _candidate_from_unmatched(unmatched)
    if unmatched.resolution_status != UnmatchedBookingStatus.OPEN:
        existing_bookings = [
            item
            for item in repository.load_bookings()
            if item.trip_instance_id in trip_instance_ids
            and item.airline == candidate.airline
            and item.origin_airport == candidate.origin_airport
            and item.destination_airport == candidate.destination_airport
            and item.departure_date == candidate.departure_date
            and item.departure_time == candidate.departure_time
            and item.record_locator == candidate.record_locator
        ]
        if len(existing_bookings) == 1:
            return existing_bookings[0]
        return None
    matching_trip_instance_ids = [
        item
        for item in _matching_trip_instance_ids_for_booking(candidate, repository.load_trackers())
        if item in trip_instance_ids
    ]
    if len(matching_trip_instance_ids) != 1:
        return None
    return resolve_unmatched_booking_to_trip_instance(
        repository,
        unmatched_booking_id=unmatched_booking_id,
        trip_instance_id=matching_trip_instance_ids[0],
    )


def unlink_booking(
    repository: Repository,
    *,
    booking_id: str,
) -> Booking:
    bookings = repository.load_bookings()
    booking = next((item for item in bookings if item.booking_id == booking_id), None)
    if booking is None or booking.status != "active":
        raise KeyError("Booking not found")
    return _unlink_booking_record(repository, booking)


def unlink_bookings_for_trip_instance(
    repository: Repository,
    *,
    trip_instance_id: str,
) -> list[Booking]:
    linked_bookings = [
        item
        for item in repository.load_bookings()
        if item.trip_instance_id == trip_instance_id
    ]
    return [_unlink_booking_record(repository, booking) for booking in linked_bookings]


def unlink_bookings_for_trip(
    repository: Repository,
    *,
    trip_id: str,
) -> list[Booking]:
    trip_instance_ids = {
        item.trip_instance_id
        for item in repository.load_trip_instances()
        if item.trip_id == trip_id
    }
    linked_bookings = [
        item
        for item in repository.load_bookings()
        if item.trip_instance_id in trip_instance_ids
    ]
    return [_unlink_booking_record(repository, booking) for booking in linked_bookings]


def update_booking(
    repository: Repository,
    *,
    booking_id: str,
    trip_instance_id: str,
    candidate: BookingCandidate,
) -> Booking:
    bookings = repository.load_bookings()
    existing = next((item for item in bookings if item.booking_id == booking_id), None)
    if existing is None:
        raise KeyError("Booking not found")
    if existing.status != BookingStatus.ACTIVE:
        raise ValueError("Only active bookings can be edited.")
    if not trip_instance_id:
        raise ValueError("Choose a scheduled trip or unlink the booking instead.")

    app_state = repository.load_app_state()
    include_test_data = include_test_data_for_processing(app_state) or str(existing.data_scope) == DataScope.TEST
    trip_instances = filter_items(repository.load_trip_instances(), include_test_data=include_test_data)
    trackers = filter_items(repository.load_trackers(), include_test_data=include_test_data)
    selected_trip = next((item for item in trip_instances if item.trip_instance_id == trip_instance_id), None)
    if selected_trip is None or selected_trip.deleted:
        raise ValueError("Choose a valid scheduled trip.")

    updated = Booking(
        booking_id=existing.booking_id,
        source=existing.source,
        trip_instance_id=selected_trip.trip_instance_id,
        route_option_id=_route_option_id_for_booking(
            candidate,
            trackers,
            trip_instance_id=selected_trip.trip_instance_id,
        ),
        data_scope=selected_trip.data_scope,
        airline=candidate.airline,
        origin_airport=candidate.origin_airport,
        destination_airport=candidate.destination_airport,
        departure_date=candidate.departure_date,
        departure_time=candidate.departure_time,
        arrival_time=candidate.arrival_time,
        booked_price=candidate.booked_price,
        record_locator=candidate.record_locator,
        booked_at=existing.booked_at,
        status=existing.status,
        notes=candidate.notes,
        created_at=existing.created_at,
        updated_at=utcnow(),
    )
    repository.upsert_bookings([updated])
    return updated


def cancel_booking(
    repository: Repository,
    *,
    booking_id: str,
) -> Booking:
    bookings = repository.load_bookings()
    booking = next((item for item in bookings if item.booking_id == booking_id), None)
    if booking is None:
        raise KeyError("Booking not found")
    if booking.status != BookingStatus.ACTIVE:
        raise ValueError("Only active bookings can be cancelled.")
    booking.status = BookingStatus.CANCELLED
    booking.updated_at = utcnow()
    repository.upsert_bookings([booking])
    return booking


def restore_booking(
    repository: Repository,
    *,
    booking_id: str,
) -> Booking:
    bookings = repository.load_bookings()
    booking = next((item for item in bookings if item.booking_id == booking_id), None)
    if booking is None:
        raise KeyError("Booking not found")
    if booking.status != BookingStatus.CANCELLED:
        raise ValueError("Only cancelled bookings can be restored.")
    booking.status = BookingStatus.ACTIVE
    booking.updated_at = utcnow()
    repository.upsert_bookings([booking])
    return booking


def delete_booking_record(
    repository: Repository,
    *,
    booking_id: str,
) -> None:
    if any(item.booking_id == booking_id for item in repository.load_bookings()):
        repository.delete_bookings_by_ids([booking_id])
        return
    if any(item.unmatched_booking_id == booking_id for item in repository.load_unmatched_bookings()):
        repository.delete_unmatched_bookings_by_ids([booking_id])
        return
    raise KeyError("Booking not found")
