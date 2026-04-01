from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.catalog import catalogs_json
from app.services.bookings import BookingCandidate, record_booking
from app.services.dashboard import load_snapshot, trip_focus_url
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(tags=["bookings"])


@router.get("/bookings", response_class=HTMLResponse)
def bookings_index(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    active_bookings = [booking for booking in snapshot.bookings if booking.status == "active"]
    open_unmatched = [item for item in snapshot.unmatched_bookings if item.resolution_status == "open"]
    return get_templates(request).TemplateResponse(
        request=request,
        name="bookings.html",
        context=base_context(
            request,
            page="bookings",
            snapshot=snapshot,
            active_bookings=sorted(active_bookings, key=lambda item: (item.departure_date, item.departure_time)),
            open_unmatched=open_unmatched,
        ),
    )


@router.get("/bookings/new", response_class=HTMLResponse)
def new_booking(
    request: Request,
    repository: Repository = Depends(get_repository),
    trip_instance_id: str | None = None,
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    selected_trip_instance = next(
        (item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id),
        None,
    ) if trip_instance_id else None
    return get_templates(request).TemplateResponse(
        request=request,
        name="booking_form.html",
        context=base_context(
            request,
            page="bookings",
            snapshot=snapshot,
            trip_instances=sorted(snapshot.trip_instances, key=lambda item: (item.anchor_date, item.display_label)),
            selected_trip_instance=selected_trip_instance,
            catalogs_json=catalogs_json(),
            booking_form_state={
                "trip_instance_id": selected_trip_instance.trip_instance_id if selected_trip_instance else "",
                "airline": "",
                "origin_airport": "",
                "destination_airport": "",
                "departure_date": "",
                "departure_time": "",
                "arrival_time": "",
                "booked_price": "",
                "record_locator": "",
                "notes": "",
            },
        ),
    )


@router.post("/bookings")
async def save_booking(
    request: Request,
    repository: Repository = Depends(get_repository),
):
    form = await request.form()
    booking_state = {
        "trip_instance_id": str(form.get("trip_instance_id", "")).strip(),
        "airline": str(form.get("airline", "")).strip(),
        "origin_airport": str(form.get("origin_airport", "")).strip(),
        "destination_airport": str(form.get("destination_airport", "")).strip(),
        "departure_date": str(form.get("departure_date", "")).strip(),
        "departure_time": str(form.get("departure_time", "")).strip(),
        "arrival_time": str(form.get("arrival_time", "")).strip(),
        "booked_price": str(form.get("booked_price", "")).strip(),
        "record_locator": str(form.get("record_locator", "")).strip(),
        "notes": str(form.get("notes", "")).strip(),
    }
    try:
        candidate = BookingCandidate(
            airline=booking_state["airline"],
            origin_airport=booking_state["origin_airport"],
            destination_airport=booking_state["destination_airport"],
            departure_date=date.fromisoformat(booking_state["departure_date"]),
            departure_time=booking_state["departure_time"],
            arrival_time=booking_state["arrival_time"],
            booked_price=int(booking_state["booked_price"]),
            record_locator=booking_state["record_locator"],
            notes=booking_state["notes"],
        )
        booking, unmatched = record_booking(
            repository,
            candidate,
            trip_instance_id=booking_state["trip_instance_id"],
            tracker_id=str(form.get("tracker_id", "")).strip(),
        )
        sync_and_persist(repository)
        if unmatched is not None:
            return RedirectResponse(url="/resolve?message=Booking+needs+resolution", status_code=303)
        if booking is None:
            raise HTTPException(status_code=500, detail="Booking was not saved.")
        snapshot = load_snapshot(repository)
        trip_instance = next(
            (item for item in snapshot.trip_instances if item.trip_instance_id == booking.trip_instance_id),
            None,
        )
        if trip_instance is None:
            return RedirectResponse(url="/bookings?message=Booking+saved", status_code=303)
        return RedirectResponse(
            url=trip_focus_url(snapshot, trip_instance.trip_id, trip_instance_id=trip_instance.trip_instance_id),
            status_code=303,
        )
    except ValueError as exc:
        snapshot = load_snapshot(repository)
        selected_trip_instance = next(
            (item for item in snapshot.trip_instances if item.trip_instance_id == booking_state["trip_instance_id"]),
            None,
        ) if booking_state["trip_instance_id"] else None
        return get_templates(request).TemplateResponse(
            request=request,
            name="booking_form.html",
            context=base_context(
                request,
                page="bookings",
                snapshot=snapshot,
                error_message=str(exc),
                trip_instances=sorted(snapshot.trip_instances, key=lambda item: (item.anchor_date, item.display_label)),
                selected_trip_instance=selected_trip_instance,
                catalogs_json=catalogs_json(),
                booking_form_state=booking_state,
            ),
            status_code=400,
        )
