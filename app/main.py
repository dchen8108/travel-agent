from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.api import router as api_router
from app.routes.bookings import router as bookings_router
from app.routes.groups import router as groups_router
from app.routes.spa import router as spa_router
from app.routes.trackers import router as trackers_router
from app.routes.trips import router as trips_router
from app.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="travel-agent")
    settings = settings or get_settings()
    app.state.settings = settings
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
