from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.money import format_money
from app.services.google_flights import generated_tracker_seed_summary
from app.services.dashboard import (
    booking_route_tracking_state,
    bookings_for_instance,
    best_tracker,
    booking_for_instance,
    comparison_tracker,
    fetch_targets_for_tracker,
    group_for_instance,
    groups_for_instance,
    horizon_instances_for_rule,
    horizon_instances_for_trip,
    load_snapshot,
    rebook_savings,
    recurring_rule_for_instance,
    trip_lifecycle_status_label,
    trip_lifecycle_status_tone,
    trip_monitoring_status_label,
    trip_recommended_action,
    trip_status_detail,
    tracker_detail_url,
    trackers_for_instance,
    trip_focus_url,
    trip_for_instance,
)
from app.services.refresh_queue import queued_refresh_message, queue_refresh_for_trip_instance
from app.services.data_scope import include_test_data_for_processing
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates, redirect_with_message

router = APIRouter(tags=["trackers"])


@dataclass(frozen=True)
class TrackerCardView:
    tracker: object
    tracker_id: str
    rank: int
    search_count: int
    departure_window_label: str
    fare_policy_label: str
    preference_note: str
    headline: str
    summary: str
    last_updated_label: str
    next_refresh_label: str
    is_retrying: bool
    has_diagnostics: bool
    fetch_targets: list
    generated_seed_summary: str


def _format_tracker_timestamp(value) -> str:
    if value is None:
        return "Not yet"
    hour = value.strftime("%I").lstrip("0") or "12"
    return f"{value.strftime('%b %d')}, {hour}:{value.strftime('%M %p')}"


def _tracker_monitor_state(tracker, fetch_targets) -> dict[str, object]:
    last_finished_at = max(
        (target.last_fetch_finished_at for target in fetch_targets if target.last_fetch_finished_at),
        default=None,
    )
    next_refresh_at = min(
        (target.next_fetch_not_before for target in fetch_targets if target.next_fetch_not_before),
        default=None,
    )
    failed_targets = [target for target in fetch_targets if target.last_fetch_status == "failed"]
    unavailable_targets = [
        target
        for target in fetch_targets
        if target.last_fetch_status in {"no_results", "no_window_match"}
    ]
    no_results_reason = next((target.last_fetch_error for target in unavailable_targets if target.last_fetch_error), "")
    if tracker.latest_observed_price is not None:
        return {
            "last_updated_at": tracker.last_signal_at or last_finished_at,
            "next_refresh_at": next_refresh_at,
            "is_retrying": bool(failed_targets),
            "all_no_results": False,
            "no_results_count": len(unavailable_targets),
            "no_results_reason": "",
        }
    if failed_targets:
        return {
            "last_updated_at": last_finished_at,
            "next_refresh_at": next_refresh_at,
            "is_retrying": True,
            "all_no_results": False,
            "no_results_count": len(unavailable_targets),
            "no_results_reason": no_results_reason,
        }
    return {
        "last_updated_at": last_finished_at,
        "next_refresh_at": next_refresh_at,
        "is_retrying": False,
        "all_no_results": bool(fetch_targets) and len(unavailable_targets) == len(fetch_targets),
        "no_results_count": len(unavailable_targets),
        "no_results_reason": no_results_reason,
    }


def _tracker_preference_note(tracker) -> str:
    if tracker.preference_bias_dollars <= 0:
        return "Treated equally with the other route options."
    return f"Needs ${tracker.preference_bias_dollars} more savings to outrank higher options."


def _tracker_card_view(snapshot, tracker) -> TrackerCardView:
    fetch_targets = fetch_targets_for_tracker(snapshot, tracker.tracker_id)
    monitor = _tracker_monitor_state(tracker, fetch_targets)
    if tracker.latest_observed_price is not None:
        headline = format_money(tracker.latest_observed_price)
        summary_parts = []
        if tracker.latest_winning_origin_airport and tracker.latest_winning_destination_airport:
            summary_parts.append(
                f"{tracker.latest_winning_origin_airport} → {tracker.latest_winning_destination_airport}"
            )
        if tracker.latest_match_summary:
            summary_parts.append(tracker.latest_match_summary)
        summary = " · ".join(summary_parts) or "Lowest current fare for this option."
    elif monitor["all_no_results"]:
        headline = "No matching flights"
        summary = str(monitor["no_results_reason"] or "No matching flights returned right now.")
    elif monitor["is_retrying"]:
        headline = "Refreshing again soon"
        summary = "A recent Google Flights request failed. Milemark will retry automatically."
    elif fetch_targets:
        headline = "Fetching current fares"
        summary = "Milemark is still collecting the first live price for this option."
    else:
        headline = "Preparing searches"
        summary = "Milemark is still setting up coverage for this option."
    return TrackerCardView(
        tracker=tracker,
        tracker_id=tracker.tracker_id,
        rank=tracker.rank,
        search_count=len(fetch_targets),
        departure_window_label=f"{tracker.travel_date.isoformat()} · {tracker.start_time}–{tracker.end_time} departure",
        fare_policy_label=(
            "Includes Basic fares"
            if tracker.fare_class_policy == "include_basic"
            else "Excludes Basic fares"
        ),
        preference_note=_tracker_preference_note(tracker),
        headline=headline,
        summary=summary,
        last_updated_label=_format_tracker_timestamp(monitor["last_updated_at"]),
        next_refresh_label=_format_tracker_timestamp(monitor["next_refresh_at"]),
        is_retrying=bool(monitor["is_retrying"]),
        has_diagnostics=bool(fetch_targets) or not bool(tracker.latest_observed_price),
        fetch_targets=fetch_targets,
        generated_seed_summary=generated_tracker_seed_summary(tracker),
    )


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
    snapshot = load_snapshot(repository)
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
    tracker_cards = [_tracker_card_view(snapshot, tracker) for tracker in trackers]
    recurring_rule = recurring_rule_for_instance(snapshot, trip_instance_id)
    trip_group = group_for_instance(snapshot, trip_instance_id)
    trip_groups = groups_for_instance(snapshot, trip_instance_id)
    sibling_parent = recurring_rule or parent_trip
    sibling_instances = [
        instance
        for instance in (
            horizon_instances_for_rule(snapshot, sibling_parent.trip_id, today=date.today())
            if recurring_rule
            else horizon_instances_for_trip(snapshot, sibling_parent.trip_id, today=date.today())
        )
        if instance.trip_instance_id != trip_instance_id
    ]
    booking = booking_for_instance(snapshot, trip_instance_id)
    bookings = bookings_for_instance(snapshot, trip_instance_id)
    booking_views = [
        {
            "booking": linked_booking,
            "route_tracking": booking_route_tracking_state(snapshot, linked_booking),
        }
        for linked_booking in bookings
    ]
    untracked_booking_count = sum(
        1 for item in booking_views if item["route_tracking"].get("warning")
    )
    active_bookings = [item for item in bookings if item.status == "active"]
    best_current_tracker = best_tracker(snapshot, trip_instance_id)
    comparison = comparison_tracker(snapshot, trip_instance_id)
    lifecycle_label = trip_lifecycle_status_label(snapshot, trip_instance_id)
    lifecycle_tone = trip_lifecycle_status_tone(snapshot, trip_instance_id)
    monitoring_label = trip_monitoring_status_label(snapshot, trip_instance_id)
    action_label = trip_recommended_action(snapshot, trip_instance_id)
    status_detail = trip_status_detail(snapshot, trip_instance_id)
    savings = rebook_savings(snapshot, trip_instance_id)
    current_fare_label = (
        format_money(comparison.latest_observed_price)
        if comparison and comparison.latest_observed_price is not None
        else "None yet"
    )
    if len(active_bookings) == 1 and booking is not None:
        booked_fare_label = format_money(booking.booked_price)
    elif len(active_bookings) > 1:
        booked_fare_label = f"{len(active_bookings)} active"
    else:
        booked_fare_label = "Not booked"
    fare_snapshot_note = ""
    if booking and len(active_bookings) > 1 and savings is not None and comparison and comparison.latest_observed_price is not None:
        fare_snapshot_note = (
            f"There are {len(active_bookings)} active bookings linked to this trip. "
            f"The latest booked fare is {format_money(booking.booked_price)}, and the best current trip option is "
            f"{format_money(comparison.latest_observed_price)}."
        )
    elif booking and len(active_bookings) > 1:
        fare_snapshot_note = (
            f"There are {len(active_bookings)} active bookings linked to this trip. "
            f"The latest booked fare is {format_money(booking.booked_price)}."
        )
    elif booking and savings is not None and comparison and comparison.latest_observed_price is not None:
        fare_snapshot_note = (
            f"Milemark found a better current trip option at {format_money(comparison.latest_observed_price)}, "
            f"{format_money(savings)} below what you booked."
        )
    elif booking and comparison and comparison.latest_observed_price is not None:
        fare_snapshot_note = (
            f"Booked at {format_money(booking.booked_price)}. "
            f"The best current trip option is {format_money(comparison.latest_observed_price)}."
        )
    elif booking:
        fare_snapshot_note = (
            f"Booked at {format_money(booking.booked_price)}. "
            "A current trip-level comparison fare is not available yet."
        )
    elif trackers and not (best_current_tracker and best_current_tracker.latest_observed_price is not None):
        fare_snapshot_note = "Milemark is still checking the monitored searches for this date."
    can_delete_parent_trip = (
        parent_trip.trip_kind == "one_time"
        and parent_trip.active
        and booking is None
    )
    can_detach_trip_instance = (
        trip_instance.inheritance_mode == "attached"
        and recurring_rule is not None
        and booking is None
    )
    can_delete_generated_trip_instance = can_detach_trip_instance

    return get_templates(request).TemplateResponse(
        request=request,
        name="trip_instance_detail.html",
        context=base_context(
            request,
            page="trips",
            snapshot=snapshot,
            trip_instance=trip_instance,
            parent_trip=parent_trip,
            recurring_rule=recurring_rule,
            trip_group=trip_group,
            trip_groups=trip_groups,
            sibling_parent=sibling_parent,
            tracker_cards=tracker_cards,
            total_fetch_targets=total_fetch_targets,
            sibling_instances=sibling_instances,
            bookings=bookings,
            booking_views=booking_views,
            untracked_booking_count=untracked_booking_count,
            active_bookings=active_bookings,
            booking=booking,
            can_delete_parent_trip=can_delete_parent_trip,
            can_detach_trip_instance=can_detach_trip_instance,
            can_delete_generated_trip_instance=can_delete_generated_trip_instance,
            best_tracker=best_current_tracker,
            comparison_tracker=comparison,
            current_fare_label=current_fare_label,
            booked_fare_label=booked_fare_label,
            fare_snapshot_note=fare_snapshot_note,
            lifecycle_label=lifecycle_label,
            lifecycle_tone=lifecycle_tone,
            monitoring_label=monitoring_label,
            action_label=action_label,
            status_detail=status_detail,
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
