from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.catalog import catalogs_json
from app.money import parse_money
from app.models.base import DataScope
from app.services.gmail_client import gmail_auth_status
from app.services.gmail_config import load_gmail_integration_config
from app.services.bookings import BookingCandidate, record_booking, unlink_booking
from app.services.dashboard import load_snapshot, trip_for_instance, trip_instance_by_id
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates, redirect_back, redirect_with_message

router = APIRouter(tags=["bookings"])


def _booking_views(snapshot):
    active_bookings = sorted(
        [booking for booking in snapshot.bookings if booking.status == "active"],
        key=lambda item: (item.departure_date, item.departure_time),
    )
    cards: list[dict[str, object]] = []
    for booking in active_bookings:
        trip_instance = trip_instance_by_id(snapshot, booking.trip_instance_id)
        parent_trip = trip_for_instance(snapshot, booking.trip_instance_id) if trip_instance else None
        cards.append(
            {
                "booking": booking,
                "trip_instance": trip_instance,
                "parent_trip": parent_trip,
            }
        )
    return cards


def _booking_email_overview(snapshot) -> dict[str, object]:
    recent_events = snapshot.booking_email_events[:8]
    counts: dict[str, int] = {}
    for event in snapshot.booking_email_events:
        counts[str(event.processing_status)] = counts.get(str(event.processing_status), 0) + 1
    return {
        "recent_events": recent_events,
        "counts": counts,
    }


@router.get("/bookings", response_class=HTMLResponse)
def bookings_index(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    open_unmatched = [item for item in snapshot.unmatched_bookings if item.resolution_status == "open"]
    gmail_config = load_gmail_integration_config(repository.settings)
    email_overview = _booking_email_overview(snapshot)
    return get_templates(request).TemplateResponse(
        request=request,
        name="bookings.html",
        context=base_context(
            request,
            page="bookings",
            snapshot=snapshot,
            booking_views=_booking_views(snapshot),
            open_unmatched=open_unmatched,
            gmail_auth=gmail_auth_status(repository.settings),
            gmail_integration=gmail_config,
            recent_email_events=email_overview["recent_events"],
            booking_email_counts=email_overview["counts"],
        ),
    )


@router.get("/bookings/new", response_class=HTMLResponse)
def new_booking(
    request: Request,
    repository: Repository = Depends(get_repository),
    trip_instance_id: str | None = None,
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    selectable_trip_instances = sorted(
        [
            item
            for item in snapshot.trip_instances
            if (
                (parent_trip := trip_for_instance(snapshot, item.trip_instance_id)) is None
                or parent_trip.trip_kind != "one_time"
                or parent_trip.active
            )
        ],
        key=lambda item: (item.anchor_date, item.display_label),
    )
    selected_trip_instance = next(
        (item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id),
        None,
    ) if trip_instance_id else None
    selected_parent_trip = trip_for_instance(snapshot, selected_trip_instance.trip_instance_id) if selected_trip_instance else None
    return get_templates(request).TemplateResponse(
        request=request,
        name="booking_form.html",
        context=base_context(
            request,
            page="bookings",
            snapshot=snapshot,
            trip_instances=selectable_trip_instances,
            selected_trip_instance=selected_trip_instance,
            selected_parent_trip=selected_parent_trip,
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
        booked_price = parse_money(booking_state["booked_price"])
        if booked_price is None:
            raise ValueError("Booked price is required.")
        candidate = BookingCandidate(
            airline=booking_state["airline"],
            origin_airport=booking_state["origin_airport"],
            destination_airport=booking_state["destination_airport"],
            departure_date=date.fromisoformat(booking_state["departure_date"]),
            departure_time=booking_state["departure_time"],
            arrival_time=booking_state["arrival_time"],
            booked_price=booked_price,
            record_locator=booking_state["record_locator"],
            notes=booking_state["notes"],
        )
        booking, unmatched = record_booking(
            repository,
            candidate,
            trip_instance_id=booking_state["trip_instance_id"],
            data_scope=str(form.get("data_scope", DataScope.LIVE)).strip() or DataScope.LIVE,
        )
        sync_and_persist(repository)
        if unmatched is not None:
            return redirect_with_message("/resolve", "Booking needs resolution")
        if booking is None:
            raise HTTPException(status_code=500, detail="Booking was not saved.")
        snapshot = load_snapshot(repository)
        trip_instance = next(
            (item for item in snapshot.trip_instances if item.trip_instance_id == booking.trip_instance_id),
            None,
        )
        if trip_instance is None:
            return redirect_with_message("/bookings", "Booking saved")
        return redirect_with_message(f"/trip-instances/{trip_instance.trip_instance_id}", "Booking saved")
    except ValueError as exc:
        snapshot = load_snapshot(repository)
        selectable_trip_instances = sorted(
            [
                item
                for item in snapshot.trip_instances
                if (
                    (parent_trip := trip_for_instance(snapshot, item.trip_instance_id)) is None
                    or parent_trip.trip_kind != "one_time"
                    or parent_trip.active
                )
            ],
            key=lambda item: (item.anchor_date, item.display_label),
        )
        selected_trip_instance = next(
            (item for item in snapshot.trip_instances if item.trip_instance_id == booking_state["trip_instance_id"]),
            None,
        ) if booking_state["trip_instance_id"] else None
        selected_parent_trip = trip_for_instance(snapshot, selected_trip_instance.trip_instance_id) if selected_trip_instance else None
        return get_templates(request).TemplateResponse(
            request=request,
            name="booking_form.html",
            context=base_context(
                request,
                page="bookings",
                snapshot=snapshot,
                error_message=str(exc),
                trip_instances=selectable_trip_instances,
                selected_trip_instance=selected_trip_instance,
                selected_parent_trip=selected_parent_trip,
                catalogs_json=catalogs_json(),
                booking_form_state=booking_state,
            ),
            status_code=400,
        )


@router.post("/bookings/{booking_id}/unlink")
def unlink_booking_action(
    booking_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    try:
        unlink_booking(repository, booking_id=booking_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    sync_and_persist(repository)
    return redirect_back(
        request,
        fallback_url="/bookings",
        message="Booking moved to Resolve",
    )
