from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models.base import TrackerStatus, utcnow
from app.services.dashboard import best_tracker, load_snapshot, trackers_for_instance, trip_focus_url
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(tags=["trackers"])


@router.get("/trackers", response_class=HTMLResponse)
def trackers_index(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    grouped: dict[str, list] = defaultdict(list)
    trip_instances_by_id = {item.trip_instance_id: item for item in snapshot.trip_instances}
    for tracker in snapshot.trackers:
        grouped[tracker.trip_instance_id].append(tracker)
    ordered_groups = [
        (trip_instances_by_id[trip_instance_id], sorted(trackers, key=lambda item: item.rank))
        for trip_instance_id, trackers in sorted(
            grouped.items(),
            key=lambda item: (trip_instances_by_id[item[0]].anchor_date, trip_instances_by_id[item[0]].display_label),
        )
    ]
    return get_templates(request).TemplateResponse(
        request=request,
        name="trackers.html",
        context=base_context(
            request,
            page="trackers",
            snapshot=snapshot,
            ordered_groups=ordered_groups,
            best_tracker=best_tracker,
            trackers_for_instance=trackers_for_instance,
            trip_focus_url=trip_focus_url,
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
    repository.save_trackers(trackers)
    sync_and_persist(repository)
    return RedirectResponse(url="/trackers?message=Tracker+updated", status_code=303)


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
    tracker.google_flights_url = str(form.get("google_flights_url", "")).strip()
    tracker.link_source = "manual" if tracker.google_flights_url else "generated"
    repository.save_trackers(trackers)
    sync_and_persist(repository)
    return RedirectResponse(url="/trackers?message=Tracker+link+saved", status_code=303)
