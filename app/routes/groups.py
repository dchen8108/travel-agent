from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.dashboard import (
    active_booking_count_for_instance,
    best_tracker,
    booking_for_instance,
    horizon_instances_for_rule,
    load_snapshot,
    recurring_rules_for_group,
    scheduled_instances,
    trackers_for_instance,
    trip_group_by_id,
    trip_groups,
    trip_for_instance,
)
from app.services.groups import delete_trip_group, save_trip_group
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates, redirect_back, redirect_with_message

router = APIRouter(tags=["groups"])


def _group_form_state(group=None):
    if group is None:
        return {
            "trip_group_id": "",
            "label": "",
            "description": "",
        }
    return {
        "trip_group_id": group.trip_group_id,
        "label": group.label,
        "description": group.description,
    }


def _render_group_form(
    request: Request,
    *,
    snapshot,
    group,
    group_form_state,
    error_message: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return get_templates(request).TemplateResponse(
        request=request,
        name="group_form.html",
        context=base_context(
            request,
            page="trips",
            snapshot=snapshot,
            group=group,
            group_form_state=group_form_state,
            error_message=error_message or "",
        ),
        status_code=status_code,
    )


@router.get("/groups/new", response_class=HTMLResponse)
def new_group(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    return _render_group_form(
        request,
        snapshot=snapshot,
        group=None,
        group_form_state=_group_form_state(None),
    )


@router.get("/groups/{trip_group_id}", response_class=HTMLResponse)
def group_detail(
    trip_group_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    group = trip_group_by_id(snapshot, trip_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Trip group not found")

    today = date.today()
    recurring_rules = recurring_rules_for_group(snapshot, trip_group_id)
    grouped_instances = scheduled_instances(snapshot, trip_group_ids={trip_group_id}, today=today)
    planned_count = sum(
        1
        for instance in grouped_instances
        if active_booking_count_for_instance(snapshot, instance.trip_instance_id) == 0
    )
    booked_count = sum(
        1
        for instance in grouped_instances
        if active_booking_count_for_instance(snapshot, instance.trip_instance_id) > 0
    )
    next_instance = next(iter(grouped_instances), None)

    return get_templates(request).TemplateResponse(
        request=request,
        name="group_detail.html",
        context=base_context(
            request,
            page="trips",
            snapshot=snapshot,
            group=group,
            recurring_rules=recurring_rules,
            grouped_instances=grouped_instances,
            planned_count=planned_count,
            booked_count=booked_count,
            next_instance=next_instance,
            today=today,
            best_tracker=best_tracker,
            booking_for_instance=booking_for_instance,
            trackers_for_instance=trackers_for_instance,
            trip_for_instance=trip_for_instance,
            horizon_instances_for_rule=horizon_instances_for_rule,
        ),
    )


@router.get("/groups/{trip_group_id}/edit", response_class=HTMLResponse)
def edit_group(
    trip_group_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    group = trip_group_by_id(snapshot, trip_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Trip group not found")
    return _render_group_form(
        request,
        snapshot=snapshot,
        group=group,
        group_form_state=_group_form_state(group),
    )


@router.post("/groups")
async def save_group_action(
    request: Request,
    repository: Repository = Depends(get_repository),
):
    form = await request.form()
    group_id = str(form.get("trip_group_id", "")).strip() or None
    label = str(form.get("label", "")).strip()
    description = str(form.get("description", "")).strip()
    try:
        group = save_trip_group(
            repository,
            trip_group_id=group_id,
            label=label,
            description=description,
        )
    except ValueError as exc:
        snapshot = load_snapshot(repository)
        existing_group = trip_group_by_id(snapshot, group_id) if group_id else None
        return _render_group_form(
            request,
            snapshot=snapshot,
            group=existing_group,
            group_form_state={
                "trip_group_id": group_id or "",
                "label": label,
                "description": description,
            },
            error_message=str(exc),
            status_code=400,
        )
    return redirect_with_message(f"/groups/{group.trip_group_id}", "Trip group saved")


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
            fallback_url=f"/groups/{trip_group_id}",
            message=str(exc),
            message_kind="error",
        )
    return redirect_with_message("/#dashboard-groups", "Trip group deleted")
