from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.bookings import (
    create_one_time_trip_from_unmatched_booking,
    resolve_unmatched_booking_to_trip_instance,
)
from app.services.dashboard import is_past_instance, load_snapshot
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates, redirect_with_message

router = APIRouter(tags=["resolve"])


@router.get("/resolve", response_class=HTMLResponse)
def resolve_index(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    open_unmatched = [item for item in snapshot.unmatched_bookings if item.resolution_status == "open"]
    trip_instances = sorted(
        [
            item
            for item in snapshot.trip_instances
            if (
                (trip := next((candidate for candidate in snapshot.trips if candidate.trip_id == item.trip_id), None)) is None
                or trip.trip_kind != "one_time"
                or trip.active
            )
        ],
        key=lambda item: (
            is_past_instance(item),
            item.travel_state == "skipped",
            item.anchor_date,
            item.display_label.lower(),
        ),
    )
    return get_templates(request).TemplateResponse(
        request=request,
        name="resolve.html",
        context=base_context(
            request,
            page="resolve",
            snapshot=snapshot,
            open_unmatched=open_unmatched,
            trip_instances=trip_instances,
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
        return redirect_with_message("/resolve", "Booking linked")
    return redirect_with_message(f"/trip-instances/{trip_instance.trip_instance_id}", "Booking linked")


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
        return redirect_with_message("/resolve", "Could not create trip")
    snapshot = sync_and_persist(repository)
    trip_instance = next(
        (item for item in snapshot.trip_instances if item.trip_instance_id == booking.trip_instance_id),
        None,
    )
    if trip_instance is None:
        return redirect_with_message("/resolve", "Trip created from booking")
    return redirect_with_message(f"/trip-instances/{trip_instance.trip_instance_id}", "Trip created from booking")
