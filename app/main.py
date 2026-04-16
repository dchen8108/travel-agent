from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routes.api import router as api_router
from app.routes.bookings import router as bookings_router
from app.routes.groups import router as groups_router
from app.routes.spa import router as spa_router
from app.routes.trackers import router as trackers_router
from app.routes.trips import router as trips_router
from app.settings import Settings, get_settings


def _compute_asset_version(static_dir: Path) -> str:
    latest_mtime_ns = 0
    for path in static_dir.rglob("*"):
        if path.is_file():
            latest_mtime_ns = max(latest_mtime_ns, path.stat().st_mtime_ns)
    return str(latest_mtime_ns or 1)


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="travel-agent")
    settings = settings or get_settings()
    app.state.settings = settings
    app.state.templates = Jinja2Templates(directory=str(settings.templates_dir))
    app.state.asset_version = _compute_asset_version(settings.static_dir)
    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
    app.mount(
        "/assets",
        StaticFiles(directory=str(settings.frontend_dist_dir / "assets"), check_dir=False),
        name="frontend-assets",
    )
    app.mount(
        "/app/assets",
        StaticFiles(directory=str(settings.frontend_dist_dir / "assets"), check_dir=False),
        name="app-assets",
    )
    app.include_router(api_router)
    app.include_router(spa_router)
    app.include_router(trips_router)
    app.include_router(groups_router)
    app.include_router(bookings_router)
    app.include_router(trackers_router)
    return app


app = create_app()
