from __future__ import annotations

from datetime import date

from app.models.tracker import Tracker
from app.services.itinerary_display import (
    booking_route_label,
    format_departure_time_label,
    tracker_best_fetch_target,
    tracker_display_label,
    travel_day_delta_label,
)
from app.services.scheduled_trip_state import (
    booking_for_instance,
    best_tracker,
    comparison_tracker,
    trackers_for_instance,
    trip_monitoring_status_label,
)
from app.services.snapshot_queries import (
    fetch_targets_for_tracker,
    group_for_instance,
    recurring_rule_for_instance,
    trip_for_instance,
    trip_instance_by_id,
)
from app.services.snapshots import AppSnapshot
from app.money import format_money


def trip_ui_label(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    group = group_for_instance(snapshot, trip_instance_id)
    if group is not None:
        return group.label
    trip = trip_for_instance(snapshot, trip_instance_id)
    if trip is not None:
        return trip.label
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    return instance.display_label if instance is not None else ""


def trip_ui_context_label(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    title = trip_ui_label(snapshot, trip_instance_id)
    trip = trip_for_instance(snapshot, trip_instance_id)
    if group_for_instance(snapshot, trip_instance_id) is not None:
        if trip is not None and trip.label and trip.label != title:
            return trip.label
        return ""
    recurring_rule = recurring_rule_for_instance(snapshot, trip_instance_id)
    if recurring_rule is not None and (trip is None or recurring_rule.trip_id != trip.trip_id):
        return recurring_rule.label
    return ""


def _row_tracker(snapshot: AppSnapshot, trip_instance_id: str) -> Tracker | None:
    tracker = comparison_tracker(snapshot, trip_instance_id)
    if tracker is not None:
        return tracker
    trackers = trackers_for_instance(snapshot, trip_instance_id)
    return trackers[0] if trackers else None


def trip_row_summary(snapshot: AppSnapshot, trip_instance_id: str) -> dict[str, object]:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    booking = booking_for_instance(snapshot, trip_instance_id)
    tracker = comparison_tracker(snapshot, trip_instance_id)
    display_tracker = _row_tracker(snapshot, trip_instance_id)
    monitoring_label = trip_monitoring_status_label(snapshot, trip_instance_id)
    current_target = tracker_best_fetch_target(
        display_tracker,
        fetch_targets_for_tracker(snapshot, display_tracker.tracker_id) if display_tracker is not None else [],
    )
    current_price = tracker.latest_observed_price if tracker is not None else None

    current_offer: dict[str, object] | None = None
    current_offer_label = "Live best"
    current_offer_price = ""
    current_offer_href = ""
    current_offer_tone = "success" if booking is None else "accent"
    current_offer_price_is_status = False
    if current_price is not None:
        current_offer_price = format_money(current_price)
        current_offer_href = current_target.google_flights_url if current_target and current_target.google_flights_url else ""
    else:
        current_offer_price = "N/A" if monitoring_label == "No matches" else "Checking"
        current_offer_tone = "neutral"
        current_offer_price_is_status = True

    current_offer_detail = tracker_display_label(display_tracker, current_target=current_target if current_price is not None else None)
    if current_offer_detail or current_offer_price:
        current_offer_meta_label = (
            format_departure_time_label(current_target.latest_departure_label)
            if current_target is not None and current_price is not None
            else ""
        )
        current_offer = {
            "label": current_offer_label,
            "detail": current_offer_detail,
            "meta_label": current_offer_meta_label,
            "day_delta_label": travel_day_delta_label(
                instance.anchor_date if instance is not None else date.today(),
                display_tracker.travel_date if display_tracker is not None else None,
            ),
            "price_label": current_offer_price,
            "href": current_offer_href,
            "tone": current_offer_tone,
            "price_is_status": current_offer_price_is_status,
        }

    booked_offer: dict[str, object] | None = None
    if booking is not None:
        booked_offer = {
            "label": "Booked at",
            "detail": booking_route_label(booking),
            "meta_label": format_departure_time_label(booking.departure_time),
            "day_delta_label": travel_day_delta_label(
                instance.anchor_date if instance is not None else date.today(),
                booking.departure_date,
            ),
            "price_label": format_money(booking.booked_price),
            "href": "",
            "tone": "neutral",
            "price_is_status": False,
        }

    return {
        "title": trip_ui_label(snapshot, trip_instance_id),
        "booked_offer": booked_offer,
        "current_offer": current_offer,
    }


def trip_ui_picker_label(snapshot: AppSnapshot, trip_instance_id: str) -> str:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        return ""
    label = trip_ui_label(snapshot, trip_instance_id)
    return f"{label} · {instance.anchor_date.strftime('%a, %b %d')}"


def booking_row_summary(booking_like: object, *, anchor_date: date | None = None) -> dict[str, object]:
    return {
        "title": getattr(booking_like, "record_locator", "") or "Imported booking",
        "booked_offer": {
            "label": "Booked at",
            "detail": booking_route_label(booking_like),
            "meta_label": format_departure_time_label(getattr(booking_like, "departure_time", "")),
            "day_delta_label": (
                travel_day_delta_label(
                    anchor_date,
                    getattr(booking_like, "departure_date", None),
                )
                if anchor_date is not None
                else ""
            ),
            "price_label": format_money(getattr(booking_like, "booked_price", 0)),
            "href": "",
            "tone": "neutral",
            "price_is_status": False,
        },
        "current_offer": None,
    }
