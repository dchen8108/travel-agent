from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.dashboard import load_snapshot
from app.services.trackers import mark_tracker_enabled, update_tracker_link
from app.services.workflows import recompute_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(prefix="/trackers", tags=["trackers"])


@router.get("", response_class=HTMLResponse)
def trackers_page(request: Request, repository: Repository = Depends(get_repository)) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    trips_by_id = {trip.trip_instance_id: trip for trip in snapshot.trips}
    rows: list[dict[str, object]] = []
    for tracker in sorted(snapshot.trackers, key=lambda item: (item.travel_date, item.origin_airport, item.destination_airport)):
        rows.append({"tracker": tracker, "trip": trips_by_id.get(tracker.trip_instance_id)})
    return get_templates(request).TemplateResponse(
        request=request,
        name="trackers.html",
        context=base_context(request, page="trackers", rows=rows, snapshot=snapshot),
    )


@router.post("/{tracker_id}/mark-enabled")
def enable_tracker(tracker_id: str, repository: Repository = Depends(get_repository)) -> RedirectResponse:
    trackers = repository.load_trackers()
    tracker = next(item for item in trackers if item.tracker_id == tracker_id)
    mark_tracker_enabled(tracker)
    repository.save_trackers(trackers)
    recompute_and_persist(repository)
    return RedirectResponse(url="/trackers?message=Tracker+updated", status_code=303)


@router.post("/{tracker_id}/paste-link")
async def paste_tracker_link(
    tracker_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    form = await request.form()
    trackers = repository.load_trackers()
    tracker = next(item for item in trackers if item.tracker_id == tracker_id)
    update_tracker_link(tracker, str(form.get("google_flights_url", "")))
    repository.save_trackers(trackers)
    return RedirectResponse(url="/trackers?message=Tracker+link+saved", status_code=303)
