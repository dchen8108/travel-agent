from __future__ import annotations

from datetime import date

from app.models.tracker import Tracker
from app.services.itinerary_display import (
    booking_route_label,
    format_departure_time_label,
    format_time_range_label,
    tracker_best_fetch_target,
    tracker_display_label,
    travel_day_delta,
)
from app.services.scheduled_trip_state import (
    active_booking_count_for_instance,
    booking_for_instance,
    best_tracker,
    comparison_tracker,
    trackers_for_instance,
    trip_monitoring_status_label,
)
from app.services.tracker_refresh_state import tracker_has_fresh_price
from app.services.snapshot_queries import (
    fetch_targets_for_tracker,
    group_for_instance,
    recurring_rule_for_instance,
    trip_for_instance,
    trip_instance_by_id,
)
from app.services.snapshots import AppSnapshot
from app.money import format_money


def _offer_meta_value(primary_meta_label: str = "", meta_badges: list[str] | None = None) -> tuple[str, list[str], str]:
    badges = [item for item in (meta_badges or []) if item]
    meta_label = " · ".join(part for part in [primary_meta_label, *badges] if part)
    return primary_meta_label, badges, meta_label


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


def booking_offer_summary(booking_like: object, *, anchor_date: date | None = None) -> dict[str, object]:
    departure_time = getattr(booking_like, "departure_time", "")
    arrival_time = getattr(booking_like, "arrival_time", "")
    record_locator = getattr(booking_like, "record_locator", "") or ""
    booking_day_delta = (
        travel_day_delta(anchor_date, getattr(booking_like, "departure_date", None))
        if anchor_date is not None
        else 0
    )
    primary_meta_label = format_time_range_label(
        departure_time,
        arrival_time,
        fallback_day_delta=booking_day_delta,
    )
    _, badges, booking_meta = _offer_meta_value(primary_meta_label, [])
    if record_locator:
        booking_meta = " · ".join(part for part in [booking_meta, record_locator] if part)
    return {
        "label": f"Booking {record_locator}" if record_locator else "Booking",
        "detail": booking_route_label(booking_like),
        "primary_meta_label": primary_meta_label,
        "meta_badges": badges,
        "meta_label": booking_meta,
        "price_label": format_money(getattr(booking_like, "booked_price", 0)),
        "href": "",
        "tone": "neutral",
        "price_is_status": False,
    }


def live_fare_offer_summary(
    *,
    anchor_date: date | None,
    travel_date: date | None,
    detail: str,
    primary_meta_label: str,
    meta_badges: list[str] | None,
    price_label: str,
    href: str,
    tone: str,
    price_is_status: bool,
    status_kind: str = "",
) -> dict[str, object]:
    badges = [item for item in (meta_badges or []) if item]
    offer = {
        "label": "Live fare",
        "detail": detail,
        "primary_meta_label": primary_meta_label,
        "meta_badges": badges,
        "meta_label": primary_meta_label,
        "price_label": price_label,
        "href": href,
        "tone": tone,
        "price_is_status": price_is_status,
    }
    if status_kind:
        offer["status_kind"] = status_kind
    return offer


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
    current_price = (
        tracker.latest_observed_price
        if tracker is not None and tracker_has_fresh_price(tracker, snapshot.app_state)
        else None
    )

    current_offer: dict[str, object] | None = None
    current_offer_price = ""
    current_offer_href = ""
    current_offer_tone = "success" if booking is None else "accent"
    current_offer_price_is_status = False
    current_offer_status_kind = ""
    if current_price is not None:
        current_offer_price = format_money(current_price)
        current_offer_href = current_target.google_flights_url if current_target and current_target.google_flights_url else ""
    else:
        current_offer_price = "N/A" if monitoring_label == "No matches" else "Checking"
        current_offer_tone = "neutral"
        current_offer_price_is_status = True
        current_offer_status_kind = "unavailable" if current_offer_price == "N/A" else "pending"

    current_offer_detail = tracker_display_label(display_tracker, current_target=current_target if current_price is not None else None)
    if current_offer_detail or current_offer_price:
        current_offer_primary_meta = (
            format_time_range_label(
                current_target.latest_departure_label,
                current_target.latest_arrival_label,
                fallback_day_delta=(
                    travel_day_delta(instance.anchor_date, display_tracker.travel_date)
                    if instance is not None and display_tracker is not None
                    else 0
                ),
            )
            if current_target is not None and current_price is not None
            else ""
        )
        current_offer = live_fare_offer_summary(
            anchor_date=instance.anchor_date if instance is not None else date.today(),
            travel_date=display_tracker.travel_date if display_tracker is not None else None,
            detail=current_offer_detail,
            primary_meta_label=current_offer_primary_meta,
            meta_badges=[],
            price_label=current_offer_price,
            href=current_offer_href,
            tone=current_offer_tone,
            price_is_status=current_offer_price_is_status,
            status_kind=current_offer_status_kind,
        )

    booked_offer: dict[str, object] | None = None
    if booking is not None:
        booked_offer = booking_offer_summary(
            booking,
            anchor_date=instance.anchor_date if instance is not None else date.today(),
        )

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
        "title": "",
        "booked_offer": booking_offer_summary(booking_like, anchor_date=anchor_date),
        "current_offer": None,
    }


def trip_row_actions_view(snapshot: AppSnapshot, trip_instance_id: str) -> dict[str, object]:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    trip = trip_for_instance(snapshot, trip_instance_id)
    recurring_rule = recurring_rule_for_instance(snapshot, trip_instance_id)
    active_booking_count = active_booking_count_for_instance(snapshot, trip_instance_id)
    has_trackers = bool(trackers_for_instance(snapshot, trip_instance_id))

    if instance is None or trip is None:
        return {
            "edit_href": "",
            "can_create_booking": False,
            "show_booking_modal": False,
            "show_trackers": False,
            "delete_href": "",
            "delete_confirmation": None,
        }

    is_attached_recurring_instance = (
        trip.trip_kind == "weekly"
        and instance.inheritance_mode == "attached"
        and recurring_rule is not None
    )
    if is_attached_recurring_instance:
        edit_href = f"/trips/{recurring_rule.trip_id}/edit?trip_instance_id={instance.trip_instance_id}"
        delete_href = f"/trip-instances/{instance.trip_instance_id}/delete-generated"
        delete_confirmation = {
            "title": "Delete this generated trip?",
            "description": "This date will be removed from the recurring trip and will stop background fare checks unless you recreate it later.",
            "action": "Delete trip",
            "cancel": "Keep trip",
        }
    else:
        edit_href = f"/trips/{trip.trip_id}/edit"
        delete_href = f"/trips/{trip.trip_id}/delete" if trip.trip_kind == "one_time" and trip.active else ""
        delete_confirmation = (
            {
                "title": "Delete this one-time trip?",
                "description": "It will disappear from the active trip workflow and stop background fare checks for this date.",
                "action": "Delete trip",
                "cancel": "Keep trip",
            }
            if delete_href
            else None
        )

    return {
        "edit_href": edit_href,
        "can_create_booking": True,
        "show_booking_modal": active_booking_count > 0,
        "show_trackers": has_trackers,
        "delete_href": delete_href,
        "delete_confirmation": delete_confirmation,
    }
