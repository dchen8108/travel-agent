from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routes.bookings import router as bookings_router
from app.routes.resolve import router as resolve_router
from app.routes.review import router as review_router
from app.routes.rules import router as rules_router
from app.routes.today import router as today_router
from app.routes.trackers import router as trackers_router
from app.routes.trips import router as trips_router
from app.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="travel-agent")
    settings = settings or get_settings()
    app.state.settings = settings
    app.state.templates = Jinja2Templates(directory=str(settings.templates_dir))
    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
    app.include_router(today_router)
    app.include_router(trips_router)
    app.include_router(bookings_router)
    app.include_router(trackers_router)
    app.include_router(resolve_router)
    app.include_router(rules_router)
    app.include_router(review_router)
    return app


app = create_app()
