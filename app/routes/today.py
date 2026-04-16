from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.services.dashboard_navigation import trip_focus_url
from app.services.dashboard_page import build_dashboard_page_context
from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.snapshot_queries import trip_group_by_id
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(tags=["today"])

def _collection_editor_state(snapshot, request: Request) -> dict[str, object] | None:
    edit_group_id = str(request.query_params.get("edit_group_id", "")).strip()
    if edit_group_id:
        group = trip_group_by_id(snapshot, edit_group_id)
        if group is None:
            return None
        return {
            "mode": "edit",
            "trip_group_id": group.trip_group_id,
            "label": group.label,
            "cancel_url": f"/#group-{group.trip_group_id}",
            "error_message": "",
        }
    if request.query_params.get("create_group"):
        return {
            "mode": "create",
            "trip_group_id": "",
            "label": "",
            "cancel_url": "/#dashboard-groups",
            "error_message": "",
        }
    return None


@router.get("/", response_class=HTMLResponse)
def today(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_persisted_snapshot(repository)
    today = date.today()
    selected_trip_group_ids = request.query_params.getlist("trip_group_id")
    include_booked = request.query_params.get("include_booked", "true").lower() != "false"
    dashboard_context = build_dashboard_page_context(
        snapshot,
        today=today,
        selected_trip_group_ids=selected_trip_group_ids,
        include_booked=include_booked,
        collection_editor_state=_collection_editor_state(snapshot, request),
    )
    partial = request.query_params.get("partial")
    if partial in {"scheduled", "scheduled-results"}:
        template_name = (
            "partials/scheduled_trips_section.html"
            if partial == "scheduled"
            else "partials/scheduled_trips_results.html"
        )
        return get_templates(request).TemplateResponse(
            request=request,
            name=template_name,
            context=base_context(
                request,
                page="dashboard",
                snapshot=snapshot,
                trip_focus_url=trip_focus_url,
                **dashboard_context,
            ),
        )
    return get_templates(request).TemplateResponse(
        request=request,
        name="today.html",
        context=base_context(
            request,
            page="dashboard",
            snapshot=snapshot,
            trip_focus_url=trip_focus_url,
            **dashboard_context,
        ),
    )
