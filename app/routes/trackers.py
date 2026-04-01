from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.google_flights import generated_tracker_seed_summary
from app.services.dashboard import (
    best_tracker,
    booking_for_instance,
    fetch_targets_for_tracker,
    horizon_instances_for_trip,
    load_snapshot,
    tracker_detail_url,
    trackers_for_instance,
    trip_focus_url,
    trip_for_instance,
)
from app.services.refresh_queue import queued_refresh_message, queue_refresh_for_trip_instance
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates, redirect_with_message

router = APIRouter(tags=["trackers"])


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


@router.get("/trackers", response_class=HTMLResponse)
def trackers_index() -> RedirectResponse:
    return RedirectResponse(url="/trips", status_code=303)


@router.post("/trackers/queue-refresh")
def queue_tracker_refresh_legacy() -> RedirectResponse:
    return RedirectResponse(url="/trips?message=Open+a+trip+and+use+View+trackers+to+refresh+its+searches.", status_code=303)


@router.get("/trip-instances/{trip_instance_id}", response_class=HTMLResponse)
@router.get("/trip-instances/{trip_instance_id}/trackers", response_class=HTMLResponse)
def trackers_detail(
    trip_instance_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    trip_instance = next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)
    if trip_instance is None:
        raise HTTPException(status_code=404, detail="Scheduled trip not found")
    parent_trip = trip_for_instance(snapshot, trip_instance_id)
    if parent_trip is None:
        raise HTTPException(status_code=404, detail="Parent trip not found")

    trackers = trackers_for_instance(snapshot, trip_instance_id)
    total_fetch_targets = sum(len(fetch_targets_for_tracker(snapshot, tracker.tracker_id)) for tracker in trackers)
    tracker_monitor_by_id = {
        tracker.tracker_id: _tracker_monitor_state(tracker, fetch_targets_for_tracker(snapshot, tracker.tracker_id))
        for tracker in trackers
    }
    sibling_instances = [
        instance
        for instance in horizon_instances_for_trip(snapshot, parent_trip.trip_id, today=date.today())
        if instance.trip_instance_id != trip_instance_id
    ]

    return get_templates(request).TemplateResponse(
        request=request,
        name="trip_instance_detail.html",
        context=base_context(
            request,
            page="trips",
            snapshot=snapshot,
            trip_instance=trip_instance,
            parent_trip=parent_trip,
            trackers=trackers,
            total_fetch_targets=total_fetch_targets,
            sibling_instances=sibling_instances,
            booking=booking_for_instance(snapshot, trip_instance_id),
            best_tracker=best_tracker(snapshot, trip_instance_id),
            fetch_targets_for_tracker=fetch_targets_for_tracker,
            generated_tracker_seed_summary=generated_tracker_seed_summary,
            tracker_monitor_by_id=tracker_monitor_by_id,
            format_tracker_timestamp=_format_tracker_timestamp,
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

    queued_count = queue_refresh_for_trip_instance(snapshot, repository, trip_instance_id=trip_instance_id)
    if queued_count == 0:
        return redirect_with_message(tracker_detail_url(trip_instance_id), "Nothing to refresh yet.")
    return redirect_with_message(
        tracker_detail_url(trip_instance_id),
        queued_refresh_message("Refresh queued", queued_count),
    )
