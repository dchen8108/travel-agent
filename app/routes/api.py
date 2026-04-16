from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from pydantic import BaseModel

from app.money import parse_money
from app.models.base import DataScope
from app.services.bookings import (
    BookingCandidate,
    delete_booking_record,
    record_booking,
    unlink_booking,
    update_booking,
)
from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.frontend_api import (
    booking_panel_payload,
    collection_card_value,
    dashboard_payload,
    tracker_panel_payload,
)
from app.services.groups import delete_trip_group, save_trip_group
from app.services.trip_instances import delete_generated_trip_instance
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
    bookedPrice: str
    recordLocator: str = ""
    notes: str = ""


def _booking_candidate(body: BookingBody) -> BookingCandidate:
    if not body.airline.strip():
        raise HTTPException(status_code=400, detail="Choose an airline.")
    if not body.originAirport.strip():
        raise HTTPException(status_code=400, detail="Choose an origin airport.")
    if not body.destinationAirport.strip():
        raise HTTPException(status_code=400, detail="Choose a destination airport.")
    if not body.departureTime.strip():
        raise HTTPException(status_code=400, detail="Departure time is required.")
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
        booked_price=booked_price,
        record_locator=body.recordLocator.strip(),
        notes=body.notes.strip(),
    )


@router.get("/dashboard")
def dashboard_api(
    trip_group_id: list[str] | None = None,
    include_booked: bool = True,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    snapshot = load_persisted_snapshot(repository)
    return dashboard_payload(
        snapshot,
        today=date.today(),
        selected_trip_group_ids=trip_group_id,
        include_booked=include_booked,
    )


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
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    try:
        group = save_trip_group(
            repository,
            trip_group_id=None,
            label=body.label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sync_and_persist(repository)
    snapshot = load_persisted_snapshot(repository)
    return collection_card_value(snapshot, group.trip_group_id, today=date.today())


@router.patch("/collections/{trip_group_id}")
def update_collection_api(
    trip_group_id: str,
    body: CollectionBody,
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    try:
        group = save_trip_group(
            repository,
            trip_group_id=trip_group_id,
            label=body.label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sync_and_persist(repository)
    snapshot = load_persisted_snapshot(repository)
    return collection_card_value(snapshot, group.trip_group_id, today=date.today())


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
    repository: Repository = Depends(get_repository),
) -> dict[str, object]:
    try:
        set_trip_active(repository, trip_id, body.active)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    sync_and_persist(repository)
    snapshot = load_persisted_snapshot(repository)
    return {"tripId": trip_id, "active": body.active, "collections": dashboard_payload(snapshot, today=date.today())["collections"]}


@router.delete("/trip-instances/{trip_instance_id}", status_code=204)
def delete_trip_instance_api(
    trip_instance_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
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
    sync_and_persist(repository)
    return Response(status_code=204)


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
    sync_and_persist(repository)
    snapshot = load_persisted_snapshot(repository)
    return booking_panel_payload(snapshot, trip_instance_id=body.tripInstanceId, mode="list")


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
    sync_and_persist(repository)
    snapshot = load_persisted_snapshot(repository)
    return booking_panel_payload(snapshot, trip_instance_id=body.tripInstanceId, mode="list")


@router.post("/bookings/{booking_id}/unlink", status_code=204)
def unlink_booking_api(
    booking_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
    try:
        unlink_booking(repository, booking_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    sync_and_persist(repository)
    return Response(status_code=204)


@router.delete("/bookings/{booking_id}", status_code=204)
def delete_booking_api(
    booking_id: str,
    repository: Repository = Depends(get_repository),
) -> Response:
    try:
        delete_booking_record(repository, booking_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    sync_and_persist(repository)
    return Response(status_code=204)
