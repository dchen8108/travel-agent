from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models.base import TrackerStatus, utcnow
from app.services.google_flights import generated_tracker_seed_summary, normalize_google_flights_url
from app.services.dashboard import (
    best_tracker,
    fetch_targets_for_tracker,
    load_snapshot,
    trackers_for_instance,
    trip_focus_url,
)
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(tags=["trackers"])


@dataclass(frozen=True)
class TrackerMonitorState:
    label: str
    tone: str
    detail: str
    last_updated_at: datetime | None
    next_refresh_at: datetime | None


def _format_tracker_timestamp(value) -> str:
    if value is None:
        return "Not yet"
    hour = value.strftime("%I").lstrip("0") or "12"
    return f"{value.strftime('%b %d')}, {hour}:{value.strftime('%M %p')}"


def _tracker_monitor_state(tracker, fetch_targets) -> TrackerMonitorState:
    last_finished_at = max(
        (target.last_fetch_finished_at for target in fetch_targets if target.last_fetch_finished_at),
        default=None,
    )
    next_refresh_at = min(
        (target.next_fetch_not_before for target in fetch_targets if target.next_fetch_not_before),
        default=None,
    )
    failed_targets = [target for target in fetch_targets if target.last_fetch_status == "failed"]
    if tracker.latest_observed_price is not None:
        return TrackerMonitorState(
            label="Auto tracking on",
            tone="success",
            detail="Google Flights links are refreshing in the background.",
            last_updated_at=tracker.last_signal_at or last_finished_at,
            next_refresh_at=next_refresh_at,
        )
    if failed_targets:
        return TrackerMonitorState(
            label="Refresh retrying",
            tone="warning",
            detail="A recent Google Flights fetch failed. Travel Agent will try again automatically.",
            last_updated_at=last_finished_at,
            next_refresh_at=next_refresh_at,
        )
    return TrackerMonitorState(
        label="Waiting for first price",
        tone="neutral",
        detail="Travel Agent has queued this tracker and is waiting for the first usable Google Flights price.",
        last_updated_at=last_finished_at,
        next_refresh_at=next_refresh_at,
    )


@router.get("/trackers", response_class=HTMLResponse)
def trackers_index(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    today = date.today()
    grouped: dict[str, list] = defaultdict(list)
    trip_instances_by_id = {item.trip_instance_id: item for item in snapshot.trip_instances}
    for tracker in snapshot.trackers:
        trip_instance = trip_instances_by_id.get(tracker.trip_instance_id)
        if trip_instance is None or trip_instance.anchor_date < today:
            continue
        grouped[tracker.trip_instance_id].append(tracker)
    ordered_groups = [
        (trip_instances_by_id[trip_instance_id], sorted(trackers, key=lambda item: item.rank))
        for trip_instance_id, trackers in sorted(
            grouped.items(),
            key=lambda item: (trip_instances_by_id[item[0]].anchor_date, trip_instances_by_id[item[0]].display_label),
        )
    ]
    tracker_monitor_by_id = {}
    for _, trackers in ordered_groups:
        for tracker in trackers:
            tracker_monitor_by_id[tracker.tracker_id] = _tracker_monitor_state(
                tracker,
                fetch_targets_for_tracker(snapshot, tracker.tracker_id),
            )
    return get_templates(request).TemplateResponse(
        request=request,
        name="trackers.html",
        context=base_context(
            request,
            page="trackers",
            snapshot=snapshot,
            ordered_groups=ordered_groups,
            best_tracker=best_tracker,
            fetch_targets_for_tracker=fetch_targets_for_tracker,
            trackers_for_instance=trackers_for_instance,
            trip_focus_url=trip_focus_url,
            generated_tracker_seed_summary=generated_tracker_seed_summary,
            tracker_monitor_by_id=tracker_monitor_by_id,
            format_tracker_timestamp=_format_tracker_timestamp,
        ),
    )


@router.post("/trackers/{tracker_id}/mark-enabled")
def mark_tracker_enabled(
    tracker_id: str,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    trackers = repository.load_trackers()
    tracker = next((item for item in trackers if item.tracker_id == tracker_id), None)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Tracker not found")
    tracker.tracking_status = TrackerStatus.TRACKING_ENABLED
    if tracker.tracking_enabled_at is None:
        tracker.tracking_enabled_at = utcnow()
    tracker.updated_at = utcnow()
    repository.save_trackers(trackers)
    sync_and_persist(repository)
    return RedirectResponse(url="/trackers?message=Background+tracking+enabled", status_code=303)


@router.post("/trackers/{tracker_id}/paste-link")
async def paste_tracker_link(
    tracker_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    trackers = repository.load_trackers()
    tracker = next((item for item in trackers if item.tracker_id == tracker_id), None)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Tracker not found")
    form = await request.form()
    try:
        tracker.google_flights_url = normalize_google_flights_url(str(form.get("google_flights_url", "")))
    except ValueError as exc:
        return RedirectResponse(url=f"/trackers?message={str(exc).replace(' ', '+')}", status_code=303)
    tracker.link_source = "manual" if tracker.google_flights_url else "generated"
    tracker.updated_at = utcnow()
    repository.save_trackers(trackers)
    sync_and_persist(repository)
    return RedirectResponse(url="/trackers?message=Legacy+tracker+link+saved", status_code=303)
