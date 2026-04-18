from __future__ import annotations

from datetime import date, timedelta

from app.money import format_money, parse_money
from app.services.scheduled_trip_state import (
    active_booking_count_for_instance,
    booking_for_instance,
    comparison_tracker,
    rebook_savings,
)


TRIP_ATTENTION_OVERBOOKED = "overbooked"
TRIP_ATTENTION_PRICE_DROP = "priceDrop"
TRIP_ATTENTION_BETTER_OPTION = "betterOption"
TRIP_ATTENTION_NEEDS_BOOKING = "needsBooking"


def rebook_attention_kind(snapshot, trip_instance_id: str) -> str | None:
    booking = booking_for_instance(snapshot, trip_instance_id)
    tracker = comparison_tracker(snapshot, trip_instance_id)
    if booking is None or tracker is None or rebook_savings(snapshot, trip_instance_id) is None:
        return None

    same_route = bool(booking.route_option_id) and booking.route_option_id == tracker.route_option_id
    booking_raw = parse_money(booking.booked_price)
    tracker_raw = parse_money(tracker.latest_observed_price)
    if same_route and booking_raw is not None and tracker_raw is not None and tracker_raw < booking_raw:
        return TRIP_ATTENTION_PRICE_DROP
    return TRIP_ATTENTION_BETTER_OPTION


def rebook_attention_title_and_badge(snapshot, trip_instance_id: str) -> tuple[str, str]:
    kind = rebook_attention_kind(snapshot, trip_instance_id)
    if kind == TRIP_ATTENTION_PRICE_DROP:
        booking = booking_for_instance(snapshot, trip_instance_id)
        tracker = comparison_tracker(snapshot, trip_instance_id)
        booking_raw = parse_money(getattr(booking, "booked_price", None))
        tracker_raw = parse_money(getattr(tracker, "latest_observed_price", None))
        if booking_raw is not None and tracker_raw is not None and tracker_raw < booking_raw:
            return "Price drop", f"{format_money(booking_raw - tracker_raw)} lower"
        return "Price drop", ""
    if kind == TRIP_ATTENTION_BETTER_OPTION:
        return "Better option after preferences", ""
    return "", ""


def dashboard_trip_attention_kind(snapshot, instance, *, today: date) -> str | None:
    active_booking_count = active_booking_count_for_instance(snapshot, instance.trip_instance_id)
    if active_booking_count > 1:
        return TRIP_ATTENTION_OVERBOOKED

    if active_booking_count > 0:
        return rebook_attention_kind(snapshot, instance.trip_instance_id)

    needs_booking_cutoff = today + timedelta(weeks=snapshot.app_state.dashboard_needs_booking_window_weeks)
    if instance.anchor_date <= needs_booking_cutoff:
        return TRIP_ATTENTION_NEEDS_BOOKING
    return None


def trip_attention_title(kind: str | None) -> str:
    return {
        TRIP_ATTENTION_OVERBOOKED: "Multiple bookings",
        TRIP_ATTENTION_PRICE_DROP: "Price drop",
        TRIP_ATTENTION_BETTER_OPTION: "Better option after preferences",
        TRIP_ATTENTION_NEEDS_BOOKING: "Needs booking",
    }.get(kind or "", "")
