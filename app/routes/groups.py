from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.services.collection_display import group_summary_view
from app.services.dashboard_page import build_dashboard_page_context
from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.groups import delete_trip_group, save_trip_group
from app.services.snapshot_queries import trip_group_by_id
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates, redirect_back, redirect_with_message

router = APIRouter(tags=["groups"])


def _dashboard_group_editor_state(
    *,
    mode: str,
    trip_group_id: str,
    label: str,
    cancel_url: str,
    error_message: str = "",
) -> dict[str, object]:
    return {
        "mode": mode,
        "trip_group_id": trip_group_id,
        "label": label,
        "cancel_url": cancel_url,
        "error_message": error_message,
    }


def _is_fetch_request(request: Request) -> bool:
    return request.headers.get("X-Requested-With", "").lower() == "fetch"


def _render_dashboard_group_editor(
    request: Request,
    *,
    snapshot,
    collection_editor_state: dict[str, object],
    status_code: int = 200,
) -> HTMLResponse:
    dashboard_context = build_dashboard_page_context(
        snapshot,
        today=date.today(),
        collection_editor_state=collection_editor_state,
    )
    return get_templates(request).TemplateResponse(
        request=request,
        name="today.html",
        context=base_context(
            request,
            page="dashboard",
            snapshot=snapshot,
            **dashboard_context,
        ),
        status_code=status_code,
    )


def _render_collection_card(
    request: Request,
    *,
    snapshot,
    trip_group_id: str,
    collection_editor_state: dict[str, object] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    group = trip_group_by_id(snapshot, trip_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Trip group not found")
    collection_card = group_summary_view(snapshot, group, today=date.today())
    return get_templates(request).TemplateResponse(
        request=request,
        name="partials/collection_summary_card.html",
        context=base_context(
            request,
            page="dashboard",
            snapshot=snapshot,
            collection_card=collection_card,
            collection_editor_state=collection_editor_state,
        ),
        status_code=status_code,
    )


def _render_collection_create_editor(
    request: Request,
    *,
    snapshot,
    collection_editor_state: dict[str, object],
    status_code: int = 200,
) -> HTMLResponse:
    return get_templates(request).TemplateResponse(
        request=request,
        name="partials/collection_inline_editor_card.html",
        context=base_context(
            request,
            page="dashboard",
            snapshot=snapshot,
            collection_editor_state=collection_editor_state,
        ),
        status_code=status_code,
    )


@router.get("/groups/new")
def new_group(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_persisted_snapshot(repository)
    return _render_dashboard_group_editor(
        request,
        snapshot=snapshot,
        collection_editor_state=_dashboard_group_editor_state(
            mode="create",
            trip_group_id="",
            label="",
            cancel_url="/#dashboard-groups",
        ),
    )


@router.get("/groups/new/inline-editor", response_class=HTMLResponse)
def new_group_inline_editor(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_persisted_snapshot(repository)
    return _render_collection_create_editor(
        request,
        snapshot=snapshot,
        collection_editor_state=_dashboard_group_editor_state(
            mode="create",
            trip_group_id="",
            label="",
            cancel_url="/#dashboard-groups",
        ),
    )


@router.get("/groups/{trip_group_id}", response_class=HTMLResponse)
def group_detail(
    trip_group_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
    snapshot = load_persisted_snapshot(repository)
    group = trip_group_by_id(snapshot, trip_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Trip group not found")
    return RedirectResponse(url=f"/#group-{group.trip_group_id}", status_code=303)


@router.get("/groups/{trip_group_id}/card", response_class=HTMLResponse)
def group_card(
    trip_group_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_persisted_snapshot(repository)
    return _render_collection_card(
        request,
        snapshot=snapshot,
        trip_group_id=trip_group_id,
    )


@router.get("/groups/{trip_group_id}/edit")
def edit_group(
    trip_group_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_persisted_snapshot(repository)
    group = trip_group_by_id(snapshot, trip_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Trip group not found")
    return _render_dashboard_group_editor(
        request,
        snapshot=snapshot,
        collection_editor_state=_dashboard_group_editor_state(
            mode="edit",
            trip_group_id=group.trip_group_id,
            label=group.label,
            cancel_url=f"/#group-{group.trip_group_id}",
        ),
    )


@router.get("/groups/{trip_group_id}/inline-editor", response_class=HTMLResponse)
def edit_group_inline_editor(
    trip_group_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_persisted_snapshot(repository)
    group = trip_group_by_id(snapshot, trip_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Trip group not found")
    return _render_collection_card(
        request,
        snapshot=snapshot,
        trip_group_id=trip_group_id,
        collection_editor_state=_dashboard_group_editor_state(
            mode="edit",
            trip_group_id=group.trip_group_id,
            label=group.label,
            cancel_url=f"/#group-{group.trip_group_id}",
        ),
    )


@router.post("/groups")
async def save_group_action(
    request: Request,
    repository: Repository = Depends(get_repository),
):
    form = await request.form()
    group_id = str(form.get("trip_group_id", "")).strip() or None
    label = str(form.get("label", "")).strip()
    try:
        group = save_trip_group(
            repository,
            trip_group_id=group_id,
            label=label,
        )
    except ValueError as exc:
        snapshot = load_persisted_snapshot(repository)
        cancel_url = str(form.get("cancel_url", "")).strip() or (
            f"/#group-{group_id}" if group_id else "/#dashboard-groups"
        )
        collection_editor_state = _dashboard_group_editor_state(
            mode="edit" if group_id else "create",
            trip_group_id=group_id or "",
            label=label,
            cancel_url=cancel_url,
            error_message=str(exc),
        )
        if _is_fetch_request(request):
            if group_id:
                return _render_collection_card(
                    request,
                    snapshot=snapshot,
                    trip_group_id=group_id,
                    collection_editor_state=collection_editor_state,
                    status_code=400,
                )
            return _render_collection_create_editor(
                request,
                snapshot=snapshot,
                collection_editor_state=collection_editor_state,
                status_code=400,
            )
        return _render_dashboard_group_editor(
            request,
            snapshot=snapshot,
            collection_editor_state=collection_editor_state,
            status_code=400,
        )
    if _is_fetch_request(request):
        snapshot = load_persisted_snapshot(repository)
        return _render_collection_card(
            request,
            snapshot=snapshot,
            trip_group_id=group.trip_group_id,
        )
    return redirect_with_message(f"/#group-{group.trip_group_id}", "Trip group saved")


@router.post("/groups/{trip_group_id}/delete")
def delete_group_action(
    trip_group_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    try:
        delete_trip_group(repository, trip_group_id=trip_group_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        return redirect_back(
            request,
            fallback_url=f"/#group-{trip_group_id}",
            message=str(exc),
            message_kind="error",
        )
    return redirect_with_message("/#dashboard-groups", "Trip group deleted")
