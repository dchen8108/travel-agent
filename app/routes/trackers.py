from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.route_details import rank_label, route_detail_label_from_fields
from app.services.dashboard import load_snapshot
from app.services.trackers import mark_tracker_enabled, update_tracker_link
from app.services.workflows import recompute_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(prefix="/trackers", tags=["trackers"])


def tracker_label(tracker) -> str:
    return route_detail_label_from_fields(
        tracker.origin_airport,
        tracker.destination_airport,
        tracker.detail_weekday,
        tracker.detail_time_start,
        tracker.detail_time_end,
        tracker.detail_airline,
    )


@router.get("", response_class=HTMLResponse)
def trackers_page(request: Request, repository: Repository = Depends(get_repository)) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    trips_by_id = {trip.trip_instance_id: trip for trip in snapshot.trips}
    programs_by_id = {program.program_id: program for program in snapshot.programs}
    grouped_rows: dict[str, dict[str, object]] = {}
    sorted_trackers = sorted(
        snapshot.trackers,
        key=lambda item: (
            item.travel_date,
            item.trip_instance_id,
            item.detail_rank,
            item.detail_time_start,
            item.detail_airline,
        ),
    )
    for tracker in sorted_trackers:
        trip = trips_by_id.get(tracker.trip_instance_id)
        if trip is None:
            continue
        group = grouped_rows.setdefault(
            tracker.trip_instance_id,
            {
                "trip": trip,
                "program": programs_by_id.get(trip.program_id),
                "trackers": [],
            },
        )
        group["trackers"].append(
            {
                "tracker": tracker,
                "detail_rank_label": rank_label(tracker.detail_rank),
                "detail_label": tracker_label(tracker),
            }
        )
    groups = list(grouped_rows.values())
    return get_templates(request).TemplateResponse(
        request=request,
        name="trackers.html",
        context=base_context(request, page="trackers", groups=groups, snapshot=snapshot),
    )


@router.post("/{tracker_id}/mark-enabled")
def enable_tracker(tracker_id: str, repository: Repository = Depends(get_repository)) -> RedirectResponse:
    trackers = repository.load_trackers()
    tracker = next((item for item in trackers if item.tracker_id == tracker_id), None)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Tracker not found")
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
    tracker = next((item for item in trackers if item.tracker_id == tracker_id), None)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Tracker not found")
    update_tracker_link(tracker, str(form.get("google_flights_url", "")))
    repository.save_trackers(trackers)
    return RedirectResponse(url="/trackers?message=Tracker+link+saved", status_code=303)
