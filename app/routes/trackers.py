from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response

from app.services.dashboard_trip_panels import trip_instance_dashboard_context
from app.services.dashboard_navigation import trip_focus_url, trip_panel_url
from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.snapshot_queries import trip_for_instance
from app.services.refresh_queue import manual_refresh_message, queue_refresh_for_trip_instance
from app.services.data_scope import include_test_data_for_processing
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import get_repository, redirect_with_message

router = APIRouter(tags=["trackers"])


def _tracker_redirect_url(snapshot, *, trip_instance_id: str, preferred_panel: str = "trackers") -> str:
    detail = trip_instance_dashboard_context(snapshot, trip_instance_id)
    panels = {
        "trackers": bool(detail["tracker_rows"]),
        "bookings": bool(detail["booking_views"]),
    }
    panel = preferred_panel if panels.get(preferred_panel) else "bookings" if panels["bookings"] else ""
    if panel:
        return trip_panel_url(
            snapshot,
            detail["parent_trip"].trip_id,
            trip_instance_id=trip_instance_id,
            panel=panel,
        )
    return trip_focus_url(snapshot, detail["parent_trip"].trip_id, trip_instance_id=trip_instance_id)


@router.get("/trackers")
def trackers_index() -> RedirectResponse:
    return RedirectResponse(url="/#all-travel", status_code=303)


@router.get("/trip-instances/{trip_instance_id}")
def trackers_detail(
    trip_instance_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
    snapshot = load_persisted_snapshot(repository)
    detail = trip_instance_dashboard_context(snapshot, trip_instance_id)
    if detail["booking_views"]:
        url = trip_panel_url(
            snapshot,
            detail["parent_trip"].trip_id,
            trip_instance_id=trip_instance_id,
            panel="bookings",
        )
    else:
        url = trip_panel_url(
            snapshot,
            detail["parent_trip"].trip_id,
            trip_instance_id=trip_instance_id,
            panel="trackers",
        )
    return RedirectResponse(url=url, status_code=303)


@router.get("/trip-instances/{trip_instance_id}/trackers")
def trackers_panel_redirect(
    trip_instance_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
    snapshot = load_persisted_snapshot(repository)
    url = _tracker_redirect_url(snapshot, trip_instance_id=trip_instance_id, preferred_panel="trackers")
    return RedirectResponse(url=url, status_code=303)


@router.get("/trip-instances/{trip_instance_id}/trackers-panel")
def trip_trackers_panel(
    trip_instance_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
    snapshot = load_persisted_snapshot(repository)
    url = _tracker_redirect_url(snapshot, trip_instance_id=trip_instance_id, preferred_panel="trackers")
    return RedirectResponse(
        url=url,
        status_code=303,
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
        manual_refresh_message(queued_count),
    )
