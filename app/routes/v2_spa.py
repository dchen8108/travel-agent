from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.routes.spa import _inject_bootstrap, _spa_index_path
from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.v2_workspace import v2_workspace_payload
from app.settings import Settings, get_settings
from app.storage.repository import Repository
from app.web import get_repository

router = APIRouter(tags=["v2-spa"])


@router.get("/v2", include_in_schema=False)
@router.get("/v2/{path:path}", include_in_schema=False)
def v2_shell(
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

    snapshot = load_persisted_snapshot(repository)
    bootstrap_payload = {
        "v2Workspace": {
            "data": v2_workspace_payload(
                snapshot,
                today=date.today(),
                repository=repository,
            )
        }
    }
    response = HTMLResponse(
        _inject_bootstrap(
            index_path.read_text(encoding="utf-8"),
            bootstrap_payload,
        )
    )
    response.headers["Cache-Control"] = "no-store"
    return response
