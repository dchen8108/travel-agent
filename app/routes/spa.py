from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.routes.api import booking_panel_api, dashboard_api, tracker_panel_api
from app.storage.repository import Repository
from app.web import get_repository
from app.settings import Settings, get_settings

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
    trip_group_ids = request.query_params.getlist("trip_group_id")
    include_booked = request.query_params.get("include_booked", "true").lower() != "false"
    bootstrap_payload: dict[str, object] = {
        "dashboard": {
            "query": _dashboard_query_string(
                trip_group_ids=trip_group_ids,
                include_booked=include_booked,
            ),
            "data": dashboard_api(
                trip_group_id=trip_group_ids or None,
                include_booked=include_booked,
                repository=repository,
            ),
        }
    }
    panel = request.query_params.get("panel", "")
    trip_instance_id = request.query_params.get("trip_instance_id", "").strip()
    if panel == "bookings" and trip_instance_id:
        mode = request.query_params.get("booking_mode", "list")
        booking_id = request.query_params.get("booking_id", "").strip()
        try:
            bootstrap_payload["bookingPanel"] = {
                "tripInstanceId": trip_instance_id,
                "mode": mode,
                "bookingId": booking_id,
                "data": booking_panel_api(
                    trip_instance_id=trip_instance_id,
                    mode=mode,
                    booking_id=booking_id,
                    repository=repository,
                ),
            }
        except HTTPException:
            pass
    if panel == "trackers" and trip_instance_id:
        try:
            bootstrap_payload["trackerPanel"] = {
                "tripInstanceId": trip_instance_id,
                "data": tracker_panel_api(
                    trip_instance_id=trip_instance_id,
                    repository=repository,
                ),
            }
        except HTTPException:
            pass
    response = HTMLResponse(_inject_bootstrap(index_path.read_text(encoding="utf-8"), bootstrap_payload))
    response.headers["Cache-Control"] = "no-store"
    return response
