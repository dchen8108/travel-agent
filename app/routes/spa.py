from __future__ import annotations

import json
from pathlib import Path

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.frontend_api import (
    booking_form_payload,
    booking_panel_payload,
    dashboard_payload,
    tracker_panel_payload,
    trip_editor_payload_for_edit,
    trip_editor_payload_for_new,
)
from app.settings import Settings, get_settings
from app.storage.repository import Repository
from app.web import get_repository

router = APIRouter(tags=["spa"])


def _spa_index_path(settings: Settings) -> Path:
    return settings.frontend_dist_dir / "index.html"


def _inject_bootstrap(index_html: str, bootstrap_payload: dict[str, object]) -> str:
    bootstrap_script = (
        "<script>"
        f"window.__MILEMARK_BOOTSTRAP__ = {json.dumps(bootstrap_payload, separators=(',', ':'))};"
        "</script>"
    )
    return index_html.replace("</body>", f"{bootstrap_script}</body>")


def _dashboard_query_string(*, trip_group_ids: list[str], include_booked: bool) -> str:
    parts = [f"trip_group_id={trip_group_id}" for trip_group_id in trip_group_ids]
    if not include_booked:
        parts.append("include_booked=false")
    return "&".join(parts)


@router.get("/", include_in_schema=False)
@router.get("/app", include_in_schema=False)
@router.get("/app/{path:path}", include_in_schema=False)
@router.get("/trips/new", include_in_schema=False)
@router.get("/trips/{trip_id}/edit", include_in_schema=False)
def app_shell(
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: Repository = Depends(get_repository),
):
    index_path = _spa_index_path(settings)
    if not index_path.exists():
        return HTMLResponse(
            """
            <html>
              <body style="font-family: sans-serif; padding: 2rem;">
                <h1>Frontend not built</h1>
                <p>Run <code>npm --prefix frontend run build</code> to build the React app.</p>
              </body>
            </html>
            """,
            status_code=503,
        )
    request_path = request.url.path.rstrip("/") or "/"
    normalized_path = (
        request_path.removeprefix("/app")
        if request_path == "/app" or request_path.startswith("/app/")
        else request_path
    ) or "/"
    trip_group_ids = request.query_params.getlist("trip_group_id")
    include_booked = request.query_params.get("include_booked", "true").lower() != "false"
    snapshot = load_persisted_snapshot(repository)
    bootstrap_payload: dict[str, object] = {}
    is_trip_editor_path = normalized_path == "/trips/new" or (
        normalized_path.startswith("/trips/") and normalized_path.endswith("/edit")
    )
    if not is_trip_editor_path:
        bootstrap_payload["dashboard"] = {
            "query": _dashboard_query_string(
                trip_group_ids=trip_group_ids,
                include_booked=include_booked,
            ),
            "data": dashboard_payload(
                snapshot,
                today=date.today(),
                selected_trip_group_ids=trip_group_ids,
                include_booked=include_booked,
            ),
        }
    panel = request.query_params.get("panel", "")
    trip_instance_id = request.query_params.get("trip_instance_id", "").strip()
    if panel == "bookings" and trip_instance_id:
        mode = request.query_params.get("booking_mode", "list")
        booking_id = request.query_params.get("booking_id", "").strip()
        bootstrap_payload["bookingPanel"] = {
            "tripInstanceId": trip_instance_id,
            "data": booking_panel_payload(
                snapshot,
                trip_instance_id=trip_instance_id,
                mode="list",
            ),
        }
        if mode in {"create", "edit"}:
            bootstrap_payload["bookingForm"] = {
                "tripInstanceId": trip_instance_id,
                "mode": mode,
                "bookingId": booking_id,
                "data": booking_form_payload(
                    snapshot,
                    trip_instance_id=trip_instance_id,
                    booking_id=booking_id if mode == "edit" else "",
                ),
            }
    if panel == "trackers" and trip_instance_id:
        bootstrap_payload["trackerPanel"] = {
            "tripInstanceId": trip_instance_id,
            "data": tracker_panel_payload(snapshot, trip_instance_id=trip_instance_id, repository=repository),
        }
    if normalized_path == "/trips/new":
        try:
            bootstrap_payload["tripEditor"] = {
                "mode": "create",
                "tripId": "",
                "query": request.url.query,
                "data": trip_editor_payload_for_new(
                    snapshot,
                    trip_kind=request.query_params.get("trip_kind", "one_time"),
                    trip_group_id=request.query_params.get("trip_group_id", ""),
                    unmatched_booking_id=request.query_params.get("unmatched_booking_id", ""),
                    trip_label=request.query_params.get("trip_label", ""),
                ),
            }
        except KeyError as error:
            raise HTTPException(status_code=404, detail=error.args[0] if error.args else "Trip not found") from error
    elif normalized_path.startswith("/trips/") and normalized_path.endswith("/edit"):
        trip_id = normalized_path.split("/")[2]
        try:
            bootstrap_payload["tripEditor"] = {
                "mode": "edit",
                "tripId": trip_id,
                "query": request.url.query,
                "data": trip_editor_payload_for_edit(
                    snapshot,
                    trip_id=trip_id,
                    trip_instance_id=request.query_params.get("trip_instance_id", ""),
                ),
            }
        except KeyError as error:
            raise HTTPException(status_code=404, detail=error.args[0] if error.args else "Trip not found") from error
    response = HTMLResponse(_inject_bootstrap(index_path.read_text(encoding="utf-8"), bootstrap_payload))
    response.headers["Cache-Control"] = "no-store"
    return response
