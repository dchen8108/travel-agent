from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, HTMLResponse

from app.settings import Settings, get_settings

router = APIRouter(tags=["spa"])


def _spa_index_path(settings: Settings) -> Path:
    return settings.frontend_dist_dir / "index.html"


@router.get("/app", include_in_schema=False)
@router.get("/app/{path:path}", include_in_schema=False)
def app_shell(
    path: str = "",
    settings: Settings = Depends(get_settings),
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
    return FileResponse(index_path)
