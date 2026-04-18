from __future__ import annotations

from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

from app.money import parse_money
from app.models.base import DataScope, FareClass, parse_fare_class
from app.services.dashboard_navigation import trip_panel_url
from app.services.bookings import (
    BookingCandidate,
    delete_booking_record,
    record_booking,
    resolve_unmatched_booking_to_trip_instance,
    unlink_booking,
    update_booking,
)
from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.scheduled_trip_state import booking_route_tracking_state
from app.services.snapshot_queries import trip_for_instance
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import get_repository, redirect_back, redirect_with_message

router = APIRouter(tags=["bookings"])


def _booking_panel_history_url(
    snapshot,
    *,
    trip_instance_id: str,
    booking_mode: str = "list",
    booking_id: str = "",
) -> str:
    parent_trip = trip_for_instance(snapshot, trip_instance_id)
    if parent_trip is None:
        return "/"
    base_url = trip_panel_url(
        snapshot,
        parent_trip.trip_id,
        trip_instance_id=trip_instance_id,
        panel="bookings",
    )
    if booking_mode == "list" and not booking_id:
        return base_url
    parsed = urlsplit(base_url)
    params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {"booking_mode", "booking_id"}
    ]
    params.append(("booking_mode", booking_mode))
    if booking_id:
        params.append(("booking_id", booking_id))
    return urlunsplit(("", "", parsed.path or "/", urlencode(params, doseq=True), parsed.fragment))


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
        return redirect_with_message("/#needs-linking", message)
    parent_trip = trip_for_instance(snapshot, trip_instance.trip_instance_id)
    if parent_trip is None:
        return redirect_with_message("/#all-travel", message)
    return redirect_with_message(
        trip_panel_url(
            snapshot,
            parent_trip.trip_id,
            trip_instance_id=trip_instance.trip_instance_id,
            panel="bookings",
        ),
        message,
    )


@router.get("/bookings")
def bookings_index(
    request: Request,
) -> RedirectResponse:
    query = request.url.query
    redirect_url = f"/?{query}#needs-linking" if query else "/#needs-linking"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/bookings/new")
def new_booking(
    repository: Repository = Depends(get_repository),
    trip_instance_id: str | None = None,
) -> Response:
    snapshot = load_persisted_snapshot(repository)
    selected_trip_instance = next(
        (item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id),
        None,
    ) if trip_instance_id else None
    if selected_trip_instance is None:
        return redirect_with_message(
            "/",
            "Start from a trip to add a booking.",
            message_kind="error",
        )
    return RedirectResponse(
        url=_booking_panel_history_url(
            snapshot,
            trip_instance_id=selected_trip_instance.trip_instance_id,
            booking_mode="create",
        ),
        status_code=303,
    )


@router.get("/bookings/{booking_id}/edit")
def edit_booking(
    booking_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
    snapshot = load_persisted_snapshot(repository)
    booking = next((item for item in snapshot.bookings if item.booking_id == booking_id), None)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if not booking.trip_instance_id:
        return redirect_with_message(
            "/#needs-linking",
            "Link this booking to a trip before editing it.",
            message_kind="error",
        )
    return RedirectResponse(
        url=_booking_panel_history_url(
            snapshot,
            trip_instance_id=booking.trip_instance_id,
            booking_mode="edit",
            booking_id=booking.booking_id,
        ),
        status_code=303,
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
        "fare_class": str(form.get("fare_class", FareClass.BASIC_ECONOMY)).strip() or FareClass.BASIC_ECONOMY,
        "booked_price": str(form.get("booked_price", "")).strip(),
        "record_locator": str(form.get("record_locator", "")).strip(),
        "notes": str(form.get("notes", "")).strip(),
    }
    try:
        if not booking_state["airline"]:
            raise ValueError("Choose an airline.")
        if not booking_state["origin_airport"]:
            raise ValueError("Choose an origin airport.")
        if not booking_state["destination_airport"]:
            raise ValueError("Choose a destination airport.")
        if not booking_state["departure_time"]:
            raise ValueError("Departure time is required.")
        fare_class = parse_fare_class(booking_state["fare_class"], default=FareClass.BASIC_ECONOMY)

        booked_price = parse_money(booking_state["booked_price"])
        if booked_price is None:
            raise ValueError("Booked price is required.")

        if booking_state["trip_instance_id"]:
            snapshot = load_persisted_snapshot(repository)
            selected_trip_instance = next(
                (item for item in snapshot.trip_instances if item.trip_instance_id == booking_state["trip_instance_id"]),
                None,
            )
            if selected_trip_instance is None:
                raise ValueError("Choose a valid scheduled trip.")

        candidate = BookingCandidate(
            airline=booking_state["airline"],
            origin_airport=booking_state["origin_airport"],
            destination_airport=booking_state["destination_airport"],
            departure_date=date.fromisoformat(booking_state["departure_date"]),
            departure_time=booking_state["departure_time"],
            arrival_time=booking_state["arrival_time"],
            fare_class=fare_class,
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
            return redirect_with_message("/#needs-linking", "Booking needs linking")
        if booking is None:
            raise HTTPException(status_code=500, detail="Booking was not saved.")
        snapshot = load_persisted_snapshot(repository)
        return _booking_redirect_response(snapshot, booking, message="Booking saved")
    except ValueError as exc:
        return PlainTextResponse(str(exc), status_code=400)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/trip-instances/{trip_instance_id}/bookings-panel")
def trip_bookings_panel(
    trip_instance_id: str,
    repository: Repository = Depends(get_repository),
    booking_mode: str = "list",
    booking_id: str = "",
) -> Response:
    snapshot = load_persisted_snapshot(repository)
    trip_instance = next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)
    if trip_instance is None:
        raise HTTPException(status_code=404, detail="Scheduled trip not found")
    if booking_mode == "edit":
        editing_booking = next((item for item in snapshot.bookings if item.booking_id == booking_id), None)
        if editing_booking is None or editing_booking.trip_instance_id != trip_instance_id:
            raise HTTPException(status_code=404, detail="Booking not found")
    elif booking_mode != "create" and booking_mode != "list":
        raise HTTPException(status_code=404, detail="Booking panel not found")
    return RedirectResponse(
        url=_booking_panel_history_url(
            snapshot,
            trip_instance_id=trip_instance_id,
            booking_mode=booking_mode,
            booking_id=booking_id,
        ),
        status_code=303,
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
            fallback_url="/#needs-linking",
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
        fallback_url="/#needs-linking",
        message="Booking needs linking",
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
        fallback_url="/",
        message="Booking deleted",
    )
