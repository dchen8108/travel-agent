from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.settings import Settings, get_settings
from app.storage.repository import Repository

templates = Jinja2Templates(directory=str(get_settings().templates_dir))


def get_repository(request: Request) -> Repository:
    settings: Settings = getattr(request.app.state, "settings", get_settings())
    repository = Repository(settings)
    repository.ensure_data_dir()
    return repository


def get_templates(request: Request) -> Jinja2Templates:
    return getattr(request.app.state, "templates", templates)


def base_context(request: Request, **extra: object) -> dict[str, object]:
    context: dict[str, object] = {
        "request": request,
        "message": request.query_params.get("message", ""),
        "message_kind": request.query_params.get("message_kind", "success"),
        "asset_version": getattr(request.app.state, "asset_version", "1"),
        "page": extra.pop("page", ""),
    }
    context.update(extra)
    return context
