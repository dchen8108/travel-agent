from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.services.dashboard_trip_panels import trip_instance_dashboard_context
from app.services.dashboard_navigation import trip_focus_url, trip_panel_url
from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.snapshot_queries import trip_for_instance
from app.services.refresh_queue import queued_refresh_message, queue_refresh_for_trip_instance
from app.services.data_scope import include_test_data_for_processing
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import back_url, base_context, get_repository, get_templates, redirect_with_message

router = APIRouter(tags=["trackers"])


@router.get("/trackers", response_class=HTMLResponse)
def trackers_index() -> RedirectResponse:
    return RedirectResponse(url="/#all-travel", status_code=303)


@router.get("/trip-instances/{trip_instance_id}", response_class=HTMLResponse)
def trackers_detail(
    trip_instance_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
    snapshot = load_persisted_snapshot(repository)
    detail = trip_instance_dashboard_context(snapshot, trip_instance_id)
    panel = "bookings" if detail["booking_views"] else "trackers" if detail["tracker_rows"] else ""
    if panel:
        url = trip_panel_url(
            snapshot,
            detail["parent_trip"].trip_id,
            trip_instance_id=trip_instance_id,
            panel=panel,
        )
    else:
        url = trip_focus_url(snapshot, detail["parent_trip"].trip_id, trip_instance_id=trip_instance_id)
    return RedirectResponse(url=url, status_code=303)


@router.get("/trip-instances/{trip_instance_id}/trackers", response_class=HTMLResponse)
def trackers_panel_redirect(
    trip_instance_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
    snapshot = load_persisted_snapshot(repository)
    detail = trip_instance_dashboard_context(snapshot, trip_instance_id)
    if detail["tracker_rows"]:
        url = trip_panel_url(
            snapshot,
            detail["parent_trip"].trip_id,
            trip_instance_id=trip_instance_id,
            panel="trackers",
        )
    elif detail["booking_views"]:
        url = trip_panel_url(
            snapshot,
            detail["parent_trip"].trip_id,
            trip_instance_id=trip_instance_id,
            panel="bookings",
        )
    else:
        url = trip_focus_url(snapshot, detail["parent_trip"].trip_id, trip_instance_id=trip_instance_id)
    return RedirectResponse(url=url, status_code=303)


@router.get("/trip-instances/{trip_instance_id}/trackers-panel", response_class=HTMLResponse)
def trip_trackers_panel(
    trip_instance_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_persisted_snapshot(repository)
    detail = trip_instance_dashboard_context(snapshot, trip_instance_id)
    return get_templates(request).TemplateResponse(
        request=request,
        name="partials/trip_trackers_panel.html",
        context=base_context(
            request,
            page="dashboard",
            snapshot=snapshot,
            **detail,
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
        return redirect_with_message(
            trip_panel_url(
                snapshot,
                trip_for_instance(snapshot, trip_instance_id).trip_id,
                trip_instance_id=trip_instance_id,
                panel="trackers",
            ),
            "Nothing to refresh yet.",
        )
    return redirect_with_message(
        trip_panel_url(
            snapshot,
            trip_for_instance(snapshot, trip_instance_id).trip_id,
            trip_instance_id=trip_instance_id,
            panel="trackers",
        ),
        queued_refresh_message("Refresh queued", queued_count),
    )
