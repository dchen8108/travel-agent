from __future__ import annotations

from datetime import date

from app.models.base import BookingStatus
from app.models.booking import Booking
from app.models.trip_instance import TripInstance
from app.route_options import split_pipe
from app.services.snapshot_queries import trip_for_instance
from app.services.snapshots import AppSnapshot


def booking_reference_label(booking: Booking) -> str:
    return f"Booking {booking.record_locator}" if booking.record_locator else "Imported booking"


def default_trip_label_for_booking(booking: Booking) -> str:
    if booking.origin_airport and booking.destination_airport:
        return f"{booking.origin_airport} to {booking.destination_airport}"
    return booking_reference_label(booking)


def selectable_trip_instances_for_booking_link(snapshot: AppSnapshot) -> list[TripInstance]:
    return sorted(
        [
            item
            for item in snapshot.trip_instances
            if not item.deleted and (
                (parent_trip := trip_for_instance(snapshot, item.trip_instance_id)) is None
                or parent_trip.trip_kind != "one_time"
                or parent_trip.active
            )
        ],
        key=lambda item: (
            item.anchor_date,
            item.display_label.lower(),
        ),
    )


def unmatched_booking_resolution_views(snapshot: AppSnapshot) -> list[dict[str, object]]:
    selectable_trip_instances = selectable_trip_instances_for_booking_link(snapshot)
    trip_instances_by_id = {item.trip_instance_id: item for item in selectable_trip_instances}
    today = date.today()
    cards: list[dict[str, object]] = []
    for unmatched in sorted(
        [
            item
            for item in snapshot.unmatched_bookings
            if item.status == BookingStatus.ACTIVE and item.needs_linking
        ],
        key=lambda item: (item.departure_date, item.departure_time, item.record_locator),
    ):
        candidate_ids = [
            item for item in split_pipe(unmatched.candidate_trip_instance_ids) if item in trip_instances_by_id
        ]
        suggested_trip_instances = [trip_instances_by_id[item] for item in candidate_ids]
        suggested_ids = {item.trip_instance_id for item in suggested_trip_instances}
        other_trip_instances = [
            item for item in selectable_trip_instances if item.trip_instance_id not in suggested_ids
        ]
        upcoming_trip_instances = [
            item for item in other_trip_instances if item.anchor_date >= today
        ]
        past_trip_instances = [
            item for item in other_trip_instances if item.anchor_date < today
        ]
        cards.append(
            {
                "unmatched": unmatched,
                "booking_reference_label": booking_reference_label(unmatched),
                "suggested_trip_label": default_trip_label_for_booking(unmatched),
                "suggested_trip_instances": suggested_trip_instances,
                "upcoming_trip_instances": upcoming_trip_instances,
                "past_trip_instances": past_trip_instances,
            }
        )
    return cards
