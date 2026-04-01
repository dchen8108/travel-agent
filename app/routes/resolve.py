from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.bookings import (
    create_one_time_trip_from_unmatched_booking,
    resolve_unmatched_booking_to_trip_instance,
)
from app.services.dashboard import load_snapshot, trip_focus_url
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(tags=["resolve"])


@router.get("/resolve", response_class=HTMLResponse)
def resolve_index(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    open_unmatched = [item for item in snapshot.unmatched_bookings if item.resolution_status == "open"]
    return get_templates(request).TemplateResponse(
        request=request,
        name="resolve.html",
        context=base_context(
            request,
            page="resolve",
            snapshot=snapshot,
            open_unmatched=open_unmatched,
            trip_instances=sorted(snapshot.trip_instances, key=lambda item: (item.anchor_date, item.display_label)),
        ),
    )


@router.post("/resolve/{unmatched_booking_id}/link")
async def resolve_link(
    unmatched_booking_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    form = await request.form()
    trip_instance_id = str(form.get("trip_instance_id", "")).strip()
    try:
        booking = resolve_unmatched_booking_to_trip_instance(
            repository,
            unmatched_booking_id=unmatched_booking_id,
            trip_instance_id=trip_instance_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    snapshot = sync_and_persist(repository)
    trip_instance = next(
        (item for item in snapshot.trip_instances if item.trip_instance_id == booking.trip_instance_id),
        None,
    )
    if trip_instance is None:
        return RedirectResponse(url="/resolve?message=Booking+linked", status_code=303)
    return RedirectResponse(
        url=trip_focus_url(snapshot, trip_instance.trip_id, trip_instance_id=trip_instance.trip_instance_id),
        status_code=303,
    )


@router.post("/resolve/{unmatched_booking_id}/create-trip")
async def resolve_create_trip(
    unmatched_booking_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    form = await request.form()
    trip_label = str(form.get("trip_label", "")).strip()
    try:
        booking = create_one_time_trip_from_unmatched_booking(
            repository,
            unmatched_booking_id=unmatched_booking_id,
            trip_label=trip_label,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError:
        return RedirectResponse(url="/resolve?message=Could+not+create+trip", status_code=303)
    snapshot = sync_and_persist(repository)
    trip_instance = next(
        (item for item in snapshot.trip_instances if item.trip_instance_id == booking.trip_instance_id),
        None,
    )
    if trip_instance is None:
        return RedirectResponse(url="/resolve?message=Trip+created+from+booking", status_code=303)
    return RedirectResponse(
        url=trip_focus_url(snapshot, trip_instance.trip_id, trip_instance_id=trip_instance.trip_instance_id),
        status_code=303,
    )
