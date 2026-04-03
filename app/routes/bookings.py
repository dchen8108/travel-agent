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
    create_one_time_trip_from_unmatched_booking,
    record_booking,
    resolve_unmatched_booking_to_trip_instance,
    unlink_booking,
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
            return redirect_with_message("/bookings#needs-linking", "Booking needs linking")
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
        selectable_trip_instances = _selectable_trip_instances(snapshot)
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
    trip_instance = next(
        (item for item in snapshot.trip_instances if item.trip_instance_id == booking.trip_instance_id),
        None,
    )
    if trip_instance is None:
        return redirect_with_message("/bookings", "Booking linked")
    return redirect_with_message(f"/trip-instances/{trip_instance.trip_instance_id}", "Booking linked")


@router.post("/bookings/unmatched/{unmatched_booking_id}/create-trip")
async def create_trip_from_unmatched_booking(
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
        return redirect_back(
            request,
            fallback_url="/bookings#needs-linking",
            message="Could not create trip from booking.",
            message_kind="error",
        )
    snapshot = sync_and_persist(repository)
    trip_instance = next(
        (item for item in snapshot.trip_instances if item.trip_instance_id == booking.trip_instance_id),
        None,
    )
    if trip_instance is None:
        return redirect_with_message("/bookings", "Trip created from booking")
    return redirect_with_message(f"/trip-instances/{trip_instance.trip_instance_id}", "Trip created from booking")


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
