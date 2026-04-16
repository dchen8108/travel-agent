from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException

from app.money import format_money
from app.services.itinerary_display import (
    fetch_target_route_label,
    format_departure_time_label,
    format_departure_window_label,
    format_refresh_timestamp_label,
    route_option_display_label,
    tracker_best_fetch_target,
)
from app.services.scheduled_trip_display import live_fare_offer_summary
from app.services.scheduled_trip_state import (
    booking_route_tracking_state,
    bookings_for_instance,
    trackers_for_instance,
)
from app.services.snapshot_queries import (
    fetch_targets_for_tracker,
    groups_for_instance,
    recurring_rule_for_instance,
    trip_for_instance,
)
from app.services.tracker_refresh_state import tracker_target_display_state


@dataclass(frozen=True)
class TrackerSearchRowView:
    row_id: str
    travel_date: date
    row: dict[str, object]


def _tracker_target_row_view(snapshot, trip_instance, tracker, target, *, is_best_target: bool) -> TrackerSearchRowView:
    display_state = tracker_target_display_state(target, snapshot.app_state)
    if display_state == "priced":
        signal_tone = "accent" if is_best_target else "neutral"
        signal_is_status = False
        signal_status_kind = ""
        headline = format_money(target.latest_price or 0)
    elif display_state == "unavailable":
        signal_tone = "neutral"
        signal_is_status = True
        signal_status_kind = "unavailable"
        headline = "N/A"
    else:
        signal_tone = "neutral"
        signal_is_status = True
        signal_status_kind = "pending"
        headline = "Checking"
    return TrackerSearchRowView(
        row_id=target.fetch_target_id,
        travel_date=tracker.travel_date,
        row={
            "title": "",
            "booked_offer": None,
            "current_offer": live_fare_offer_summary(
                anchor_date=trip_instance.anchor_date,
                travel_date=tracker.travel_date,
                detail=fetch_target_route_label(target, fallback_tracker=tracker),
                meta_label=(
                    format_departure_time_label(target.latest_departure_label)
                    if target.latest_departure_label
                    else format_departure_window_label(tracker.start_time, tracker.end_time)
                ),
                price_label=headline,
                href=target.google_flights_url if target.google_flights_url else "",
                tone=signal_tone,
                price_is_status=signal_is_status,
                status_kind=signal_status_kind,
            ),
        },
    )


def _tracker_fallback_row_view(trip_instance, tracker) -> TrackerSearchRowView:
    return TrackerSearchRowView(
        row_id=tracker.tracker_id,
        travel_date=tracker.travel_date,
        row={
            "title": "",
            "booked_offer": None,
            "current_offer": live_fare_offer_summary(
                anchor_date=trip_instance.anchor_date,
                travel_date=tracker.travel_date,
                detail=route_option_display_label(
                    tracker.origin_codes,
                    tracker.destination_codes,
                    tracker.airline_codes,
                ),
                meta_label=format_departure_window_label(tracker.start_time, tracker.end_time),
                price_label="Checking",
                href="",
                tone="neutral",
                price_is_status=True,
                status_kind="pending",
            ),
        },
    )


def tracker_search_rows(snapshot, trip_instance, tracker) -> list[TrackerSearchRowView]:
    fetch_targets = fetch_targets_for_tracker(snapshot, tracker.tracker_id)
    if not fetch_targets:
        return [_tracker_fallback_row_view(trip_instance, tracker)]
    best_target = tracker_best_fetch_target(tracker, fetch_targets)
    sorted_targets = sorted(
        fetch_targets,
        key=lambda item: (item.origin_airport, item.destination_airport, item.fetch_target_id),
    )
    return [
        _tracker_target_row_view(
            snapshot,
            trip_instance,
            tracker,
            target,
            is_best_target=best_target is not None and target.fetch_target_id == best_target.fetch_target_id,
        )
        for target in sorted_targets
    ]


def trip_instance_dashboard_context(snapshot, trip_instance_id: str) -> dict[str, object]:
    trip_instance = next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)
    if trip_instance is None or trip_instance.deleted:
        raise HTTPException(status_code=404, detail="Scheduled trip not found")
    parent_trip = trip_for_instance(snapshot, trip_instance_id)
    if parent_trip is None:
        raise HTTPException(status_code=404, detail="Parent trip not found")
    if parent_trip.trip_kind == "one_time" and not parent_trip.active:
        raise HTTPException(status_code=404, detail="Scheduled trip not found")

    trackers = trackers_for_instance(snapshot, trip_instance_id)
    total_fetch_targets = sum(len(fetch_targets_for_tracker(snapshot, tracker.tracker_id)) for tracker in trackers)
    oldest_tracker_refresh_at = min(
        (
            target.last_fetch_finished_at
            for tracker in trackers
            for target in fetch_targets_for_tracker(snapshot, tracker.tracker_id)
            if target.last_fetch_finished_at is not None
        ),
        default=None,
    )
    tracker_rows = [
        row
        for tracker in trackers
        for row in tracker_search_rows(snapshot, trip_instance, tracker)
    ]
    recurring_rule = recurring_rule_for_instance(snapshot, trip_instance_id)
    trip_groups = groups_for_instance(snapshot, trip_instance_id)
    bookings = bookings_for_instance(snapshot, trip_instance_id)
    booking_views = [
        {
            "booking": linked_booking,
            "route_tracking": booking_route_tracking_state(snapshot, linked_booking),
        }
        for linked_booking in bookings
    ]
    return {
        "trip_instance": trip_instance,
        "parent_trip": parent_trip,
        "recurring_rule": recurring_rule,
        "trip_groups": trip_groups,
        "tracker_rows": tracker_rows,
        "total_fetch_targets": total_fetch_targets,
        "tracker_refresh_footer_label": (
            f"Last refresh · {format_refresh_timestamp_label(oldest_tracker_refresh_at)}"
            if oldest_tracker_refresh_at is not None
            else ""
        ),
        "bookings": bookings,
        "booking_views": booking_views,
    }
