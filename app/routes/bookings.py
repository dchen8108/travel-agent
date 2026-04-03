from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.catalog import catalogs_json
from app.money import parse_money
from app.models.base import DataScope
from app.route_options import split_pipe
from app.services.bookings import (
    BookingCandidate,
    cancel_booking,
    delete_booking_record,
    record_booking,
    resolve_unmatched_booking_to_trip_instance,
    unlink_booking,
    update_booking,
)
from app.services.dashboard import (
    booking_route_tracking_state,
    load_snapshot,
    trip_for_instance,
    trip_instance_by_id,
)
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates, redirect_back, redirect_with_message

router = APIRouter(tags=["bookings"])


def _selectable_trip_instances(snapshot):
    return sorted(
        [
            item
            for item in snapshot.trip_instances
            if not item.deleted and (
                (parent_trip := trip_for_instance(snapshot, item.trip_instance_id)) is None
                or parent_trip.trip_kind != "one_time"
                or parent_trip.active
            )
        ],
        key=lambda item: (
            item.anchor_date,
            item.display_label.lower(),
        ),
    )


def _booking_views(snapshot):
    active_bookings = sorted(
        [booking for booking in snapshot.bookings if booking.status == "active"],
        key=lambda item: (item.departure_date, item.departure_time, item.record_locator),
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
                "route_tracking": booking_route_tracking_state(snapshot, booking),
            }
        )
    return cards


def _booking_history_views(snapshot):
    history = sorted(
        [booking for booking in snapshot.bookings if booking.status != "active"],
        key=lambda item: (item.departure_date, item.departure_time, item.record_locator),
        reverse=True,
    )
    cards: list[dict[str, object]] = []
    for booking in history:
        trip_instance = trip_instance_by_id(snapshot, booking.trip_instance_id)
        parent_trip = trip_for_instance(snapshot, booking.trip_instance_id) if trip_instance else None
        cards.append(
            {
                "booking": booking,
                "trip_instance": trip_instance,
                "parent_trip": parent_trip,
                "route_tracking": booking_route_tracking_state(snapshot, booking),
            }
        )
    return cards


def _booking_form_state(booking=None, *, trip_instance_id: str = "") -> dict[str, str]:
    if booking is None:
        return {
            "booking_id": "",
            "trip_instance_id": trip_instance_id,
            "airline": "",
            "origin_airport": "",
            "destination_airport": "",
            "departure_date": "",
            "departure_time": "",
            "arrival_time": "",
            "booked_price": "",
            "record_locator": "",
            "notes": "",
        }
    return {
        "booking_id": booking.booking_id,
        "trip_instance_id": trip_instance_id or booking.trip_instance_id,
        "airline": booking.airline,
        "origin_airport": booking.origin_airport,
        "destination_airport": booking.destination_airport,
        "departure_date": booking.departure_date.isoformat(),
        "departure_time": booking.departure_time,
        "arrival_time": booking.arrival_time,
        "booked_price": str(booking.booked_price),
        "record_locator": booking.record_locator,
        "notes": booking.notes,
    }


def _render_booking_form(
    request: Request,
    *,
    snapshot,
    trip_instances,
    booking_form_state,
    selected_trip_instance=None,
    selected_parent_trip=None,
    editing_booking=None,
    error_message: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return get_templates(request).TemplateResponse(
        request=request,
        name="booking_form.html",
        context=base_context(
            request,
            page="bookings",
            snapshot=snapshot,
            trip_instances=trip_instances,
            selected_trip_instance=selected_trip_instance,
            selected_parent_trip=selected_parent_trip,
            editing_booking=editing_booking,
            catalogs_json=catalogs_json(),
            error_message=error_message or "",
            booking_form_state=booking_form_state,
        ),
        status_code=status_code,
    )


def _booking_redirect_response(snapshot, booking, *, message: str) -> RedirectResponse:
    stored_booking = next((item for item in snapshot.bookings if item.booking_id == booking.booking_id), booking)
    trip_instance = next(
        (item for item in snapshot.trip_instances if item.trip_instance_id == stored_booking.trip_instance_id),
        None,
    )
    route_tracking = booking_route_tracking_state(snapshot, stored_booking)
    if route_tracking.get("warning"):
        message = f"{message}. {route_tracking['warning']}"
    if trip_instance is None:
        return redirect_with_message("/bookings", message)
    return redirect_with_message(f"/trip-instances/{trip_instance.trip_instance_id}", message)


def _unmatched_booking_views(snapshot):
    selectable_trip_instances = _selectable_trip_instances(snapshot)
    trip_instances_by_id = {item.trip_instance_id: item for item in selectable_trip_instances}
    cards: list[dict[str, object]] = []
    for unmatched in sorted(
        [item for item in snapshot.unmatched_bookings if item.resolution_status == "open"],
        key=lambda item: (item.departure_date, item.departure_time, item.record_locator),
    ):
        candidate_ids = [item for item in split_pipe(unmatched.candidate_trip_instance_ids) if item in trip_instances_by_id]
        suggested_trip_instances = [trip_instances_by_id[item] for item in candidate_ids]
        trip_options = suggested_trip_instances or selectable_trip_instances
        cards.append(
            {
                "unmatched": unmatched,
                "trip_options": trip_options,
                "suggested_trip_instances": suggested_trip_instances,
            }
        )
    return cards


@router.get("/bookings", response_class=HTMLResponse)
def bookings_index(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    booking_views = _booking_views(snapshot)
    history_views = _booking_history_views(snapshot)
    unmatched_views = _unmatched_booking_views(snapshot)
    return get_templates(request).TemplateResponse(
        request=request,
        name="bookings.html",
        context=base_context(
            request,
            page="bookings",
            snapshot=snapshot,
            booking_views=booking_views,
            history_views=history_views,
            unmatched_views=unmatched_views,
        ),
    )


@router.get("/bookings/new", response_class=HTMLResponse)
def new_booking(
    request: Request,
    repository: Repository = Depends(get_repository),
    trip_instance_id: str | None = None,
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    selectable_trip_instances = _selectable_trip_instances(snapshot)
    selected_trip_instance = next(
        (item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id),
        None,
    ) if trip_instance_id else None
    selected_parent_trip = trip_for_instance(snapshot, selected_trip_instance.trip_instance_id) if selected_trip_instance else None
    return _render_booking_form(
        request,
        snapshot=snapshot,
        trip_instances=selectable_trip_instances,
        selected_trip_instance=selected_trip_instance,
        selected_parent_trip=selected_parent_trip,
        booking_form_state=_booking_form_state(
            None,
            trip_instance_id=selected_trip_instance.trip_instance_id if selected_trip_instance else "",
        ),
    )


@router.get("/bookings/{booking_id}/edit", response_class=HTMLResponse)
def edit_booking(
    booking_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    booking = next((item for item in snapshot.bookings if item.booking_id == booking_id), None)
    if booking is None or booking.status != "active":
        raise HTTPException(status_code=404, detail="Booking not found")
    selectable_trip_instances = _selectable_trip_instances(snapshot)
    selected_trip_instance = next(
        (item for item in selectable_trip_instances if item.trip_instance_id == booking.trip_instance_id),
        None,
    )
    selected_parent_trip = trip_for_instance(snapshot, selected_trip_instance.trip_instance_id) if selected_trip_instance else None
    return _render_booking_form(
        request,
        snapshot=snapshot,
        trip_instances=selectable_trip_instances,
        selected_trip_instance=selected_trip_instance,
        selected_parent_trip=selected_parent_trip,
        editing_booking=booking,
        booking_form_state=_booking_form_state(booking),
    )


@router.post("/bookings")
async def save_booking(
    request: Request,
    repository: Repository = Depends(get_repository),
):
    form = await request.form()
    booking_state = {
        "booking_id": str(form.get("booking_id", "")).strip(),
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
        if booking_state["booking_id"]:
            booking = update_booking(
                repository,
                booking_id=booking_state["booking_id"],
                trip_instance_id=booking_state["trip_instance_id"],
                candidate=candidate,
            )
            unmatched = None
        else:
            booking, unmatched = record_booking(
                repository,
                candidate,
                trip_instance_id=booking_state["trip_instance_id"],
                data_scope=str(form.get("data_scope", DataScope.LIVE)).strip() or DataScope.LIVE,
            )
        sync_and_persist(repository)
        if unmatched is not None:
            return redirect_with_message("/bookings#needs-linking", "Booking needs linking")
        if booking is None:
            raise HTTPException(status_code=500, detail="Booking was not saved.")
        snapshot = load_snapshot(repository)
        return _booking_redirect_response(snapshot, booking, message="Booking saved")
    except ValueError as exc:
        snapshot = load_snapshot(repository)
        selectable_trip_instances = _selectable_trip_instances(snapshot)
        selected_trip_instance = next(
            (item for item in snapshot.trip_instances if item.trip_instance_id == booking_state["trip_instance_id"]),
            None,
        ) if booking_state["trip_instance_id"] else None
        selected_parent_trip = trip_for_instance(snapshot, selected_trip_instance.trip_instance_id) if selected_trip_instance else None
        editing_booking = next(
            (item for item in snapshot.bookings if item.booking_id == booking_state["booking_id"]),
            None,
        ) if booking_state["booking_id"] else None
        return _render_booking_form(
            request,
            snapshot=snapshot,
            trip_instances=selectable_trip_instances,
            selected_trip_instance=selected_trip_instance,
            selected_parent_trip=selected_parent_trip,
            editing_booking=editing_booking,
            error_message=str(exc),
            booking_form_state=booking_state,
            status_code=400,
        )


@router.post("/bookings/unmatched/{unmatched_booking_id}/link")
async def link_unmatched_booking(
    unmatched_booking_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    form = await request.form()
    trip_instance_id = str(form.get("trip_instance_id", "")).strip()
    if not trip_instance_id:
        return redirect_back(
            request,
            fallback_url="/bookings#needs-linking",
            message="Choose a scheduled trip first.",
            message_kind="error",
        )
    try:
        booking = resolve_unmatched_booking_to_trip_instance(
            repository,
            unmatched_booking_id=unmatched_booking_id,
            trip_instance_id=trip_instance_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    snapshot = sync_and_persist(repository)
    return _booking_redirect_response(snapshot, booking, message="Booking linked")


@router.post("/bookings/unmatched/{unmatched_booking_id}/create-trip")
async def create_trip_from_unmatched_booking(
    unmatched_booking_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    form = await request.form()
    trip_label = str(form.get("trip_label", "")).strip()
    unmatched = next(
        (item for item in repository.load_unmatched_bookings() if item.unmatched_booking_id == unmatched_booking_id),
        None,
    )
    if unmatched is None:
        raise HTTPException(status_code=404, detail="Unmatched booking not found")
    redirect_url = f"/trips/new?unmatched_booking_id={unmatched_booking_id}"
    if trip_label:
        from urllib.parse import quote_plus

        redirect_url = f"{redirect_url}&trip_label={quote_plus(trip_label)}"
    return RedirectResponse(url=redirect_url, status_code=303)


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


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking_action(
    booking_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    try:
        cancel_booking(repository, booking_id=booking_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        return redirect_back(
            request,
            fallback_url="/bookings",
            message=str(exc),
            message_kind="error",
        )
    sync_and_persist(repository)
    return redirect_back(
        request,
        fallback_url="/bookings",
        message="Booking cancelled",
    )


@router.post("/bookings/{booking_id}/delete")
def delete_booking_action(
    booking_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    try:
        delete_booking_record(repository, booking_id=booking_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    sync_and_persist(repository)
    return redirect_back(
        request,
        fallback_url="/bookings",
        message="Booking deleted",
    )
