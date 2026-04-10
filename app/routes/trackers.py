from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.money import format_money
from app.services.dashboard_navigation import tracker_detail_url, trip_focus_url
from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.itinerary_display import (
    fetch_target_route_label,
    format_departure_time_label,
    format_departure_window_label,
    route_option_display_label,
    tracker_best_fetch_target,
    travel_day_delta_label,
)
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
from app.services.refresh_queue import queued_refresh_message, queue_refresh_for_trip_instance
from app.services.data_scope import include_test_data_for_processing
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import back_url, base_context, get_repository, get_templates, redirect_with_message

router = APIRouter(tags=["trackers"])


@dataclass(frozen=True)
class TrackerSearchRowView:
    row_id: str
    travel_date: date
    row: dict[str, object]


def _tracker_target_row_view(trip_instance, tracker, target, *, is_best_target: bool) -> TrackerSearchRowView:
    if target.latest_price is not None:
        signal_label = "Live fare"
        signal_tone = "accent" if is_best_target else "neutral"
        signal_is_status = False
        headline = format_money(target.latest_price)
    elif target.last_fetch_status in {"no_results", "no_window_match"}:
        signal_label = "Live fare"
        signal_tone = "neutral"
        signal_is_status = True
        headline = "N/A"
    else:
        signal_label = "Live fare"
        signal_tone = "neutral"
        signal_is_status = True
        headline = "Checking"
    return TrackerSearchRowView(
        row_id=target.fetch_target_id,
        travel_date=tracker.travel_date,
        row={
            "title": "",
            "booked_offer": None,
            "current_offer": {
                "label": signal_label,
                "detail": fetch_target_route_label(target, fallback_tracker=tracker),
                "meta_label": (
                    format_departure_time_label(target.latest_departure_label)
                    if target.latest_departure_label
                    else format_departure_window_label(tracker.start_time, tracker.end_time)
                ),
                "day_delta_label": travel_day_delta_label(
                    trip_instance.anchor_date,
                    tracker.travel_date,
                ),
                "price_label": headline,
                "href": target.google_flights_url if target.google_flights_url else "",
                "tone": signal_tone,
                "price_is_status": signal_is_status,
            },
        },
    )


def _tracker_fallback_row_view(trip_instance, tracker) -> TrackerSearchRowView:
    return TrackerSearchRowView(
        row_id=tracker.tracker_id,
        travel_date=tracker.travel_date,
        row={
            "title": "",
            "booked_offer": None,
            "current_offer": {
                "label": "Live fare",
                "detail": route_option_display_label(
                    tracker.origin_codes,
                    tracker.destination_codes,
                    tracker.airline_codes,
                ),
                "meta_label": format_departure_window_label(tracker.start_time, tracker.end_time),
                "day_delta_label": travel_day_delta_label(
                    trip_instance.anchor_date,
                    tracker.travel_date,
                ),
                "price_label": "Checking",
                "href": "",
                "tone": "neutral",
                "price_is_status": True,
            },
        },
    )


def _tracker_search_rows(snapshot, trip_instance, tracker) -> list[TrackerSearchRowView]:
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
            trip_instance,
            tracker,
            target,
            is_best_target=best_target is not None and target.fetch_target_id == best_target.fetch_target_id,
        )
        for target in sorted_targets
    ]


@router.get("/trackers", response_class=HTMLResponse)
def trackers_index() -> RedirectResponse:
    return RedirectResponse(url="/#all-travel", status_code=303)


@router.get("/trip-instances/{trip_instance_id}", response_class=HTMLResponse)
@router.get("/trip-instances/{trip_instance_id}/trackers", response_class=HTMLResponse)
def trackers_detail(
    trip_instance_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_persisted_snapshot(repository)
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
    tracker_rows = [
        row
        for tracker in trackers
        for row in _tracker_search_rows(snapshot, trip_instance, tracker)
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
    can_delete_parent_trip = (
        parent_trip.trip_kind == "one_time"
        and parent_trip.active
    )
    can_detach_trip_instance = (
        trip_instance.inheritance_mode == "attached"
        and recurring_rule is not None
    )
    can_delete_generated_trip_instance = can_detach_trip_instance

    return get_templates(request).TemplateResponse(
        request=request,
        name="trip_instance_detail.html",
        context=base_context(
            request,
            page="trips",
            snapshot=snapshot,
            back_href=back_url(
                request,
                fallback_url=trip_focus_url(snapshot, parent_trip.trip_id, trip_instance_id=trip_instance.trip_instance_id),
            ),
            trip_instance=trip_instance,
            parent_trip=parent_trip,
            recurring_rule=recurring_rule,
            trip_groups=trip_groups,
            tracker_rows=tracker_rows,
            total_fetch_targets=total_fetch_targets,
            bookings=bookings,
            booking_views=booking_views,
            can_delete_parent_trip=can_delete_parent_trip,
            can_detach_trip_instance=can_detach_trip_instance,
            can_delete_generated_trip_instance=can_delete_generated_trip_instance,
            trip_focus_url=trip_focus_url,
            tracker_detail_url=tracker_detail_url,
        ),
    )


@router.post("/trip-instances/{trip_instance_id}/trackers/queue-refresh")
def queue_tracker_refresh(
    trip_instance_id: str,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    snapshot = sync_and_persist(repository)
    trip_instance = next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)
    if trip_instance is None:
        raise HTTPException(status_code=404, detail="Scheduled trip not found")

    queued_count = queue_refresh_for_trip_instance(
        snapshot,
        repository,
        trip_instance_id=trip_instance_id,
        include_test_data=include_test_data_for_processing(snapshot.app_state),
    )
    if queued_count == 0:
        return redirect_with_message(tracker_detail_url(trip_instance_id), "Nothing to refresh yet.")
    return redirect_with_message(
        tracker_detail_url(trip_instance_id),
        queued_refresh_message("Refresh queued", queued_count),
    )
