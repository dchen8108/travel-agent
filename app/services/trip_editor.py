from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.catalog import airline_label
from app.models.base import BookingStatus, DataScope, FareClass
from app.models.trip import Trip
from app.services.bookings import (
    BookingCandidate,
    resolve_unmatched_booking_to_trip,
    suggested_route_option_payload_for_booking,
)
from app.services.dashboard_booking_views import booking_reference_label, default_trip_label_for_booking
from app.services.dashboard_navigation import trip_focus_url, trip_panel_url
from app.services.data_scope import include_test_data_for_processing
from app.services.group_memberships import replace_manual_trip_instance_groups
from app.services.groups import find_or_create_trip_group
from app.services.refresh_queue import queue_refresh_for_trip
from app.services.snapshot_queries import (
    groups_for_rule,
    groups_for_trip,
    instances_for_rule,
    instances_for_trip,
    route_options_for_trip,
    trip_by_id,
)
from app.services.trips import save_trip
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


def trip_form_state(trip: Trip | None, *, trip_group_ids: list[str] | None = None) -> dict[str, object]:
    if trip is None:
        return {
            "tripId": "",
            "label": "",
            "tripKind": "one_time",
            "tripGroupIds": [],
            "preferenceMode": "equal",
            "anchorDate": "",
            "anchorWeekday": "Monday",
            "dataScope": DataScope.LIVE,
        }
    return {
        "tripId": trip.trip_id,
        "label": trip.label,
        "tripKind": trip.trip_kind,
        "tripGroupIds": trip_group_ids or [],
        "preferenceMode": trip.preference_mode,
        "anchorDate": trip.anchor_date.isoformat() if trip.anchor_date else "",
        "anchorWeekday": trip.anchor_weekday or "Monday",
        "dataScope": trip.data_scope,
        "createdAt": trip.created_at.isoformat(),
    }


def route_option_state(route_options) -> list[dict[str, object]]:
    return [
        {
            "routeOptionId": option.route_option_id,
            "savingsNeededVsPrevious": option.savings_needed_vs_previous,
            "originAirports": option.origin_codes,
            "destinationAirports": option.destination_codes,
            "airlines": option.airline_codes,
            "dayOffset": option.day_offset,
            "startTime": option.start_time,
            "endTime": option.end_time,
            "fareClass": option.fare_class,
        }
        for option in route_options
    ]


def route_option_payloads(route_options: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "route_option_id": str(item.get("routeOptionId", "") or ""),
            "savings_needed_vs_previous": int(item.get("savingsNeededVsPrevious", 0) or 0),
            "origin_airports": "|".join(item.get("originAirports", []) or []),
            "destination_airports": "|".join(item.get("destinationAirports", []) or []),
            "airlines": "|".join(item.get("airlines", []) or []),
            "day_offset": int(item.get("dayOffset", 0) or 0),
            "start_time": str(item.get("startTime", "") or ""),
            "end_time": str(item.get("endTime", "") or ""),
            "fare_class": str(
                item.get("fareClass", item.get("fareClassPolicy", FareClass.BASIC_ECONOMY)) or FareClass.BASIC_ECONOMY
            ),
        }
        for item in route_options
    ]


def recurring_linked_trip_warning(snapshot, trip: Trip, *, trip_instance_id: str = "") -> dict[str, object] | None:
    if trip.trip_kind != "weekly":
        return None
    linked_trip_count = sum(
        1
        for instance in instances_for_rule(snapshot, trip.trip_id)
        if not instance.deleted and instance.inheritance_mode == "attached"
    )
    detachable_trip_instance_id = ""
    if trip_instance_id:
        matching_instance = next(
            (
                instance
                for instance in instances_for_rule(snapshot, trip.trip_id)
                if instance.trip_instance_id == trip_instance_id
                and not instance.deleted
                and instance.inheritance_mode == "attached"
            ),
            None,
        )
        detachable_trip_instance_id = matching_instance.trip_instance_id if matching_instance else ""
    return {
        "linkedTripCount": linked_trip_count,
        "linkedTripLabel": "linked trip" if linked_trip_count == 1 else "linked trips",
        "detachableTripInstanceId": detachable_trip_instance_id,
    }


def new_trip_form_payload(
    snapshot,
    *,
    trip_kind: str,
    trip_group_id: str,
    unmatched_booking_id: str,
    trip_label: str,
) -> dict[str, object]:
    source_unmatched_booking = next(
        (
            item
            for item in snapshot.unmatched_bookings
            if item.unmatched_booking_id == unmatched_booking_id and item.resolution_status == "open"
        ),
        None,
    ) if unmatched_booking_id else None
    if unmatched_booking_id and source_unmatched_booking is None:
        raise KeyError("Unmatched booking not found")

    values = {
        **trip_form_state(None),
        "tripKind": trip_kind if trip_kind in {"one_time", "weekly"} else "one_time",
        "tripGroupIds": [trip_group_id] if trip_group_id else [],
    }
    routes = route_option_state([])
    source_booking = None
    if source_unmatched_booking is not None:
        candidate = BookingCandidate(
            airline=source_unmatched_booking.airline,
            origin_airport=source_unmatched_booking.origin_airport,
            destination_airport=source_unmatched_booking.destination_airport,
            departure_date=source_unmatched_booking.departure_date,
            departure_time=source_unmatched_booking.departure_time,
            arrival_time=source_unmatched_booking.arrival_time,
            fare_class=source_unmatched_booking.fare_class,
            booked_price=source_unmatched_booking.booked_price,
            record_locator=source_unmatched_booking.record_locator,
        )
        suggested_label = trip_label or default_trip_label_for_booking(source_unmatched_booking)
        values.update(
            {
                "label": suggested_label,
                "tripKind": "one_time",
                "anchorDate": source_unmatched_booking.departure_date.isoformat(),
                "dataScope": source_unmatched_booking.data_scope,
            }
        )
        suggested_route = suggested_route_option_payload_for_booking(candidate)
        routes = [
            {
                "routeOptionId": "",
                "savingsNeededVsPrevious": 0,
                "originAirports": [suggested_route["origin_airports"]],
                "destinationAirports": [suggested_route["destination_airports"]],
                "airlines": [suggested_route["airlines"]],
                "dayOffset": suggested_route["day_offset"],
                "startTime": suggested_route["start_time"],
                "endTime": suggested_route["end_time"],
                "fareClass": suggested_route["fare_class"],
            }
        ]
        source_booking = {
            "unmatchedBookingId": source_unmatched_booking.unmatched_booking_id,
            "referenceLabel": booking_reference_label(source_unmatched_booking),
            "routeLabel": f"{source_unmatched_booking.origin_airport} → {source_unmatched_booking.destination_airport}",
            "departureDate": source_unmatched_booking.departure_date.isoformat(),
            "departureTime": source_unmatched_booking.departure_time,
            "arrivalTime": source_unmatched_booking.arrival_time,
            "airlineLabel": airline_label(source_unmatched_booking.airline),
        }

    return {
        "mode": "create",
        "values": values,
        "routeOptions": routes,
        "sourceBooking": source_booking,
        "recurringEditWarning": None,
    }


def edit_trip_form_payload(snapshot, trip_id: str, *, trip_instance_id: str = "") -> dict[str, object]:
    trip = next((item for item in snapshot.trips if item.trip_id == trip_id), None)
    if trip is None or (trip.trip_kind == "one_time" and not trip.active):
        raise KeyError("Trip not found")
    routes = route_options_for_trip(snapshot, trip.trip_id)
    return {
        "mode": "edit",
        "values": trip_form_state(
            trip,
            trip_group_ids=[group.trip_group_id for group in groups_for_trip(snapshot, trip)],
        ),
        "routeOptions": route_option_state(routes),
        "sourceBooking": None,
        "recurringEditWarning": recurring_linked_trip_warning(snapshot, trip, trip_instance_id=trip_instance_id),
    }


def linked_booking_route_warning_count(snapshot, trip: Trip) -> int:
    if trip.trip_kind == "weekly":
        trip_instance_ids = {
            instance.trip_instance_id
            for instance in instances_for_rule(snapshot, trip.trip_id)
            if not instance.deleted
        }
    else:
        trip_instance_ids = {
            instance.trip_instance_id
            for instance in instances_for_trip(snapshot, trip.trip_id)
            if not instance.deleted
        }
    return sum(
        1
        for booking in snapshot.bookings
        if booking.status == BookingStatus.ACTIVE
        and booking.trip_instance_id in trip_instance_ids
        and not booking.route_option_id
    )


@dataclass
class TripSaveInput:
    trip_id: str | None
    label: str
    trip_kind: str
    trip_group_ids: list[str]
    preference_mode: str
    anchor_date: date | None
    anchor_weekday: str
    route_options: list[dict[str, object]]
    data_scope: str
    source_unmatched_booking_id: str = ""


@dataclass
class TripSaveResult:
    trip: Trip
    snapshot: object
    message: str
    redirect_to: str
    linked_booking_id: str = ""


def save_trip_workflow(
    repository: Repository,
    *,
    data: TripSaveInput,
) -> TripSaveResult:
    existing_trip = next((item for item in repository.load_trips() if item.trip_id == data.trip_id), None) if data.trip_id else None
    trip_group_ids = list(data.trip_group_ids)
    auto_created_group = False
    if data.trip_kind == "weekly" and not trip_group_ids:
        existing_rule_has_groups = bool(
            existing_trip
            and any(target.rule_trip_id == existing_trip.trip_id for target in repository.load_rule_group_targets())
        )
        if existing_trip is not None and existing_rule_has_groups:
            raise ValueError("Recurring rules must stay in at least one group.")
        if not data.label:
            raise ValueError("Trip label is required.")
        with repository.transaction():
            fallback_group = find_or_create_trip_group(
                repository,
                label=data.label,
                data_scope=data.data_scope,
            )
            trip_group_ids = [fallback_group.trip_group_id]
            trip = save_trip(
                repository,
                trip_id=data.trip_id,
                label=data.label,
                trip_kind=data.trip_kind,
                preference_mode=data.preference_mode,
                active=existing_trip.active if existing_trip else True,
                anchor_date=data.anchor_date,
                anchor_weekday=data.anchor_weekday,
                trip_group_ids=trip_group_ids,
                route_option_payloads=data.route_options,
                data_scope=data.data_scope,
            )
            auto_created_group = True
    if not auto_created_group:
        trip = save_trip(
            repository,
            trip_id=data.trip_id,
            label=data.label,
            trip_kind=data.trip_kind,
            preference_mode=data.preference_mode,
            active=existing_trip.active if existing_trip else True,
            anchor_date=data.anchor_date,
            anchor_weekday=data.anchor_weekday,
            trip_group_ids=trip_group_ids,
            route_option_payloads=data.route_options,
            data_scope=data.data_scope,
        )

    snapshot = sync_and_persist(repository)
    if trip.trip_kind == "one_time":
        replace_manual_trip_instance_groups(
            repository,
            trip_instance_ids=[
                instance.trip_instance_id
                for instance in snapshot.trip_instances
                if instance.trip_id == trip.trip_id and not instance.deleted
            ],
            trip_group_ids=trip_group_ids,
            data_scope=trip.data_scope,
        )

    linked_booking = None
    if data.source_unmatched_booking_id:
        linked_booking = resolve_unmatched_booking_to_trip(
            repository,
            unmatched_booking_id=data.source_unmatched_booking_id,
            trip_id=trip.trip_id,
        )
        snapshot = sync_and_persist(repository)

    queue_refresh_for_trip(
        snapshot,
        repository,
        trip_id=trip.trip_id,
        include_test_data=include_test_data_for_processing(snapshot.app_state),
    )
    message = "Trip created from booking" if data.source_unmatched_booking_id else "Trip saved"
    warning_count = linked_booking_route_warning_count(snapshot, trip)
    if warning_count:
        booking_noun = "booking" if warning_count == 1 else "bookings"
        verb = "does" if warning_count == 1 else "do"
        message = (
            f"{message} {warning_count} linked {booking_noun} "
            f"{verb} not match a unique tracked route."
        )

    if data.source_unmatched_booking_id and linked_booking is None:
        return TripSaveResult(
            trip=trip,
            snapshot=snapshot,
            message=f"{message} Booking still needs linking.",
            redirect_to="/#needs-linking",
        )
    if linked_booking is not None:
        return TripSaveResult(
            trip=trip,
            snapshot=snapshot,
            message=message,
            linked_booking_id=linked_booking.booking_id,
            redirect_to=trip_panel_url(
                snapshot,
                trip.trip_id,
                trip_instance_id=linked_booking.trip_instance_id,
                panel="bookings",
            ),
        )
    if trip.trip_kind == "one_time":
        active_instances = [
            instance
            for instance in instances_for_trip(snapshot, trip.trip_id)
            if not instance.deleted
        ]
        if active_instances:
            return TripSaveResult(
                trip=trip,
                snapshot=snapshot,
                message=message,
                redirect_to=trip_focus_url(snapshot, trip.trip_id, trip_instance_id=active_instances[0].trip_instance_id),
            )
    recurring_groups = groups_for_trip(snapshot, trip)
    redirect_to = f"/#group-{recurring_groups[0].trip_group_id}" if len(recurring_groups) == 1 else "/#all-travel"
    return TripSaveResult(
        trip=trip,
        snapshot=snapshot,
        message=message,
        redirect_to=redirect_to,
    )
