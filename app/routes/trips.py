from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.bookings import upsert_booking
from app.services.dashboard import load_snapshot
from app.services.workflows import recompute_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(tags=["trips"])


@router.get("/trips/{trip_instance_id}", response_class=HTMLResponse)
def trip_detail(
    trip_instance_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    trip = next(item for item in snapshot.trips if item.trip_instance_id == trip_instance_id)
    trackers = [tracker for tracker in snapshot.trackers if tracker.trip_instance_id == trip_instance_id]
    booking = next((item for item in snapshot.bookings if item.trip_instance_id == trip_instance_id and item.status == "active"), None)
    observations = [
        observation
        for observation in snapshot.observations
        if observation.trip_instance_id == trip_instance_id
    ]
    observations.sort(key=lambda item: item.observed_at, reverse=True)
    return get_templates(request).TemplateResponse(
        request=request,
        name="trip_detail.html",
        context=base_context(
            request,
            page="trip-detail",
            snapshot=snapshot,
            trip=trip,
            trackers=trackers,
            booking=booking,
            observations=observations[:20],
        ),
    )


@router.get("/bookings/new", response_class=HTMLResponse)
def add_booking_form(
    request: Request,
    repository: Repository = Depends(get_repository),
    trip_id: str | None = None,
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    trip = next((item for item in snapshot.trips if item.trip_instance_id == trip_id), None) if trip_id else None
    if trip is None and snapshot.trips:
        trip = snapshot.trips[0]
    existing = (
        next((item for item in snapshot.bookings if item.trip_instance_id == trip.trip_instance_id and item.status == "active"), None)
        if trip is not None
        else None
    )
    return get_templates(request).TemplateResponse(
        request=request,
        name="add_booking.html",
        context=base_context(
            request,
            page="booking",
            snapshot=snapshot,
            trip=trip,
            booking=existing,
            trips=snapshot.trips,
        ),
    )


@router.post("/bookings")
async def save_booking(request: Request, repository: Repository = Depends(get_repository)) -> RedirectResponse:
    form = await request.form()
    trip_id = str(form.get("trip_instance_id", ""))
    snapshot = load_snapshot(repository, recompute=False)
    trip = next(item for item in snapshot.trips if item.trip_instance_id == trip_id)
    bookings, _booking = upsert_booking(snapshot.bookings, trip, form)
    repository.save_bookings(bookings)
    repository.save_trip_instances(snapshot.trips)
    recompute_and_persist(repository)
    return RedirectResponse(url=f"/trips/{trip_id}?message=Booking+saved", status_code=303)
