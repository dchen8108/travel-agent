from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from app.money import parse_money
from app.models.base import DataScope, FareClass, parse_fare_class
from app.services.bookings import (
    BookingCandidate,
    delete_booking_record,
    record_booking,
    resolve_unmatched_booking_to_trip_instance,
    unlink_booking,
    update_booking,
    update_unmatched_booking,
)
from app.services.dashboard_snapshot import load_live_snapshot, load_persisted_snapshot
from app.services.frontend_api import (
    booking_form_payload,
    booking_panel_payload,
    collection_card_value,
    dashboard_payload,
    unmatched_booking_form_payload,
    trip_editor_payload_for_edit,
    trip_editor_payload_for_new,
    tracker_panel_payload,
)
from app.services.groups import delete_trip_group, save_trip_group
from app.services.trip_instances import delete_generated_trip_instance
from app.services.trip_instances import detach_generated_trip_instance
from app.services.refresh_queue import queue_refresh_for_trip_instance
from app.services.data_scope import filter_snapshot, include_test_data_for_processing, include_test_data_for_ui
from app.services.trip_editor import TripSaveInput, route_option_payloads, save_trip_workflow
from app.services.trips import delete_trip, set_trip_active
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import get_repository

router = APIRouter(prefix="/api", tags=["api"])


class CollectionBody(BaseModel):
    label: str


class TripStatusBody(BaseModel):
    active: bool


class BookingBody(BaseModel):
    tripInstanceId: str
    airline: str
    originAirport: str
    destinationAirport: str
    departureDate: str
    departureTime: str
    arrivalTime: str
    fareClass: str = FareClass.BASIC_ECONOMY
    flightNumber: str = ""
    bookedPrice: str
    recordLocator: str = ""
    notes: str = ""


class UnmatchedBookingLinkBody(BaseModel):
    tripInstanceId: str


class TripEditorBody(BaseModel):
    label: str
    tripKind: str
    tripGroupIds: list[str] = []
    preferenceMode: str = "equal"
    anchorDate: str = ""
    anchorWeekday: str = ""
    routeOptions: list[dict[str, object]] = []
    dataScope: str = DataScope.LIVE
    sourceUnmatchedBookingId: str = ""


def _booking_candidate(body: BookingBody) -> BookingCandidate:
    if not body.airline.strip():
        raise HTTPException(status_code=400, detail="Choose an airline.")
    if not body.originAirport.strip():
        raise HTTPException(status_code=400, detail="Choose an origin airport.")
    if not body.destinationAirport.strip():
        raise HTTPException(status_code=400, detail="Choose a destination airport.")
    if not body.departureTime.strip():
        raise HTTPException(status_code=400, detail="Departure time is required.")
    try:
        fare_class = parse_fare_class(body.fareClass, default=FareClass.BASIC_ECONOMY)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Choose a fare.") from exc
    booked_price = parse_money(body.bookedPrice)
    if booked_price is None:
        raise HTTPException(status_code=400, detail="Booked price is required.")
    try:
        departure_date = date.fromisoformat(body.departureDate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Choose a valid departure date.") from exc
    return BookingCandidate(
        airline=body.airline.strip(),
        origin_airport=body.originAirport.strip(),
        destination_airport=body.destinationAirport.strip(),
        departure_date=departure_date,
        departure_time=body.departureTime.strip(),
        arrival_time=body.arrivalTime.strip(),
        fare_class=fare_class,
        flight_number=body.flightNumber.strip(),
        booked_price=booked_price,
        record_locator=body.recordLocator.strip(),
        notes=body.notes.strip(),
    )


def _trip_save_input(body: TripEditorBody, *, trip_id: str | None = None) -> TripSaveInput:
    try:
        anchor_date = date.fromisoformat(body.anchorDate) if body.anchorDate else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Choose a valid travel date.") from exc
    return TripSaveInput(
        trip_id=trip_id,
        label=body.label.strip(),
        trip_kind=body.tripKind.strip() or "one_time",
        trip_group_ids=body.tripGroupIds,
        preference_mode=body.preferenceMode.strip() or "equal",
        anchor_date=anchor_date,
        anchor_weekday=body.anchorWeekday.strip(),
        route_options=route_option_payloads(body.routeOptions),
        data_scope=body.dataScope.strip() or DataScope.LIVE,
        source_unmatched_booking_id=body.sourceUnmatchedBookingId.strip(),
    )


def _dashboard_view_payload(
    snapshot,
    *,
    trip_group_ids: list[str] | None,
    include_booked: bool,
) -> dict[str, object]:
    filtered_snapshot = filter_snapshot(snapshot, include_test_data=include_test_data_for_ui(snapshot.app_state))
    return dashboard_payload(
        filtered_snapshot,
        today=date.today(),
        selected_trip_group_ids=trip_group_ids,
        include_booked=include_booked,
    )


@router.get("/dashboard")
def dashboard_api(
    trip_group_id: list[str] | None = Query(default=None),
    include_booked: bool = True,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    return _dashboard_view_payload(snapshot, trip_group_ids=trip_group_id, include_booked=include_booked)


@router.get("/trips/new-form")
def trip_editor_new_api(
    trip_kind: str = "one_time",
    trip_group_id: str = "",
    unmatched_booking_id: str = "",
    trip_label: str = "",
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    try:
        return trip_editor_payload_for_new(
            snapshot,
            trip_kind=trip_kind,
            trip_group_id=trip_group_id,
            unmatched_booking_id=unmatched_booking_id,
            trip_label=trip_label,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/trips/{trip_id}/edit-form")
def trip_editor_edit_api(
    trip_id: str,
    trip_instance_id: str = "",
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    try:
        return trip_editor_payload_for_edit(
            snapshot,
            trip_id=trip_id,
            trip_instance_id=trip_instance_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/trips/editor")
def create_trip_api(
    body: TripEditorBody,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    try:
        result = save_trip_workflow(repository, data=_trip_save_input(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": result.message,
        "redirectTo": result.redirect_to,
    }


@router.patch("/trips/{trip_id}/editor")
def update_trip_api(
    trip_id: str,
    body: TripEditorBody,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    try:
        result = save_trip_workflow(repository, data=_trip_save_input(body, trip_id=trip_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": result.message,
        "redirectTo": result.redirect_to,
    }


@router.get("/collections/{trip_group_id}")
def collection_api(
    trip_group_id: str,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    return collection_card_value(snapshot, trip_group_id, today=date.today())


@router.post("/collections")
def create_collection_api(
    body: CollectionBody,
    trip_group_id: list[str] | None = Query(default=None),
    include_booked: bool = True,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    try:
        save_trip_group(
            repository,
            trip_group_id=None,
            label=body.label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot = load_live_snapshot(repository)
    return {"dashboard": _dashboard_view_payload(snapshot, trip_group_ids=trip_group_id, include_booked=include_booked)}


@router.patch("/collections/{trip_group_id}")
def update_collection_api(
    trip_group_id: str,
    body: CollectionBody,
    selected_trip_group_id: list[str] | None = Query(default=None, alias="trip_group_id"),
    include_booked: bool = True,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    try:
        save_trip_group(
            repository,
            trip_group_id=trip_group_id,
            label=body.label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot = load_live_snapshot(repository)
    return {"dashboard": _dashboard_view_payload(snapshot, trip_group_ids=selected_trip_group_id, include_booked=include_booked)}


@router.delete("/collections/{trip_group_id}", status_code=204)
def delete_collection_api(
    trip_group_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
    try:
        delete_trip_group(repository, trip_group_id=trip_group_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sync_and_persist(repository)
    return Response(status_code=204)


@router.patch("/trips/{trip_id}/status")
def update_trip_status_api(
    trip_id: str,
    body: TripStatusBody,
    background_tasks: BackgroundTasks,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    try:
        set_trip_active(repository, trip_id, body.active)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    background_tasks.add_task(load_live_snapshot, repository)
    return {
        "tripId": trip_id,
        "active": body.active,
    }


@router.delete("/trip-instances/{trip_instance_id}")
def delete_trip_instance_api(
    trip_instance_id: str,
    trip_group_id: list[str] | None = Query(default=None),
    include_booked: bool = True,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    instance = next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)
    if instance is None:
        raise HTTPException(status_code=404, detail="Scheduled trip not found")
    trip = next((item for item in snapshot.trips if item.trip_id == instance.trip_id), None)
    if trip is None:
        raise HTTPException(status_code=404, detail="Parent trip not found")
    try:
        if trip.trip_kind == "one_time" and trip.active:
            delete_trip(repository, trip.trip_id)
        else:
            delete_generated_trip_instance(repository, trip_instance_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot = load_live_snapshot(repository)
    return {"dashboard": _dashboard_view_payload(snapshot, trip_group_ids=trip_group_id, include_booked=include_booked)}


@router.post("/trip-instances/{trip_instance_id}/detach")
def detach_trip_instance_api(
    trip_instance_id: str,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    try:
        trip_instance = detach_generated_trip_instance(repository, trip_instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot = sync_and_persist(repository)
    queue_refresh_for_trip_instance(
        snapshot,
        repository,
        trip_instance_id=trip_instance.trip_instance_id,
        include_test_data=include_test_data_for_processing(snapshot.app_state),
    )
    return {
        "message": "Trip detached",
        "redirectTo": f"/trips/{trip_instance.trip_id}/edit",
    }


@router.get("/trip-instances/{trip_instance_id}/bookings")
def booking_panel_api(
    trip_instance_id: str,
    mode: str = "list",
    booking_id: str = "",
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    return booking_panel_payload(
        snapshot,
        trip_instance_id=trip_instance_id,
        mode=mode,
        booking_id=booking_id,
    )


@router.get("/trip-instances/{trip_instance_id}/booking-form")
def booking_form_api(
    trip_instance_id: str,
    booking_id: str = "",
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    return booking_form_payload(
        snapshot,
        trip_instance_id=trip_instance_id,
        booking_id=booking_id,
    )


@router.get("/unmatched-bookings/{unmatched_booking_id}/form")
def unmatched_booking_form_api(
    unmatched_booking_id: str,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    return unmatched_booking_form_payload(snapshot, unmatched_booking_id=unmatched_booking_id)


@router.get("/trip-instances/{trip_instance_id}/trackers")
def tracker_panel_api(
    trip_instance_id: str,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    return tracker_panel_payload(snapshot, trip_instance_id=trip_instance_id)


@router.post("/bookings")
def create_booking_api(
    body: BookingBody,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    candidate = _booking_candidate(body)
    try:
        booking, unmatched = record_booking(
            repository,
            candidate,
            trip_instance_id=body.tripInstanceId,
            data_scope=DataScope.LIVE,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if unmatched is not None or booking is None:
        raise HTTPException(status_code=400, detail="Booking must be linked to a scheduled trip.")
    snapshot = load_live_snapshot(repository)
    return {
        "panel": booking_panel_payload(snapshot, trip_instance_id=body.tripInstanceId, mode="list"),
    }


@router.patch("/bookings/{booking_id}")
def update_booking_api(
    booking_id: str,
    body: BookingBody,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    candidate = _booking_candidate(body)
    try:
        update_booking(
            repository,
            booking_id=booking_id,
            trip_instance_id=body.tripInstanceId,
            candidate=candidate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot = load_live_snapshot(repository)
    return {
        "panel": booking_panel_payload(snapshot, trip_instance_id=body.tripInstanceId, mode="list"),
    }


@router.patch("/unmatched-bookings/{unmatched_booking_id}")
def update_unmatched_booking_api(
    unmatched_booking_id: str,
    body: BookingBody,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    candidate = _booking_candidate(body)
    try:
        update_unmatched_booking(
            repository,
            unmatched_booking_id=unmatched_booking_id,
            candidate=candidate,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    load_live_snapshot(repository)
    return {"ok": True}


@router.post("/bookings/{booking_id}/unlink")
def unlink_booking_api(
    booking_id: str,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    booking = next((item for item in snapshot.bookings if item.booking_id == booking_id), None)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    try:
        unlink_booking(repository, booking_id=booking_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    snapshot = load_live_snapshot(repository)
    return {
        "panel": booking_panel_payload(snapshot, trip_instance_id=booking.trip_instance_id, mode="list"),
    }


@router.post("/unmatched-bookings/{unmatched_booking_id}/link")
def link_unmatched_booking_api(
    unmatched_booking_id: str,
    body: UnmatchedBookingLinkBody,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    try:
        resolve_unmatched_booking_to_trip_instance(
            repository,
            unmatched_booking_id=unmatched_booking_id,
            trip_instance_id=body.tripInstanceId,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    load_live_snapshot(repository)
    return {"ok": True}


@router.delete("/bookings/{booking_id}")
def delete_booking_api(
    booking_id: str,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    booking = next((item for item in snapshot.bookings if item.booking_id == booking_id), None)
    try:
        delete_booking_record(repository, booking_id=booking_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    snapshot = load_live_snapshot(repository)
    return {
        "panel": (
            booking_panel_payload(snapshot, trip_instance_id=booking.trip_instance_id, mode="list")
            if booking is not None and booking.trip_instance_id
            else None
        ),
    }
