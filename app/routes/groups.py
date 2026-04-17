from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.groups import delete_trip_group, save_trip_group
from app.services.snapshot_queries import trip_group_by_id
from app.storage.repository import Repository
from app.web import get_repository, redirect_back, redirect_with_message

router = APIRouter(tags=["groups"])


@router.get("/groups/new")
def new_group() -> Response:
    return RedirectResponse(url="/?create_group=1#dashboard-groups", status_code=303)


@router.get("/groups/{trip_group_id}")
def group_detail(
    trip_group_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
    snapshot = load_persisted_snapshot(repository)
    group = trip_group_by_id(snapshot, trip_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return RedirectResponse(url=f"/#group-{group.trip_group_id}", status_code=303)


@router.get("/groups/{trip_group_id}/edit")
def edit_group(
    trip_group_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
    snapshot = load_persisted_snapshot(repository)
    group = trip_group_by_id(snapshot, trip_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return RedirectResponse(
        url=f"/?edit_group_id={group.trip_group_id}#group-{group.trip_group_id}",
        status_code=303,
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
        return PlainTextResponse(str(exc), status_code=400)
    return redirect_with_message(f"/#group-{group.trip_group_id}", "Collection saved")


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
    return redirect_with_message("/#dashboard-groups", "Collection deleted")
