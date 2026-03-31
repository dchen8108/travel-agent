from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.catalog import BOOKING_FARE_TYPES, SUPPORTED_AIRLINES
from app.route_details import rank_label, route_detail_label_from_fields
from app.services.bookings import upsert_booking
from app.services.dashboard import load_snapshot
from app.services.workflows import recompute_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(tags=["trips"])


def tracker_sort_key(tracker) -> tuple[int, object, str, str]:
    return (
        tracker.detail_rank,
        tracker.travel_date,
        tracker.detail_time_start,
        tracker.detail_airline,
    )


def tracker_label(tracker) -> str:
    return route_detail_label_from_fields(
        tracker.origin_airport,
        tracker.destination_airport,
        tracker.detail_weekday,
        tracker.detail_time_start,
        tracker.detail_time_end,
        tracker.detail_airline,
    )


@router.get("/trips/{trip_instance_id}", response_class=HTMLResponse)
def trip_detail(
    trip_instance_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    trip = next((item for item in snapshot.trips if item.trip_instance_id == trip_instance_id), None)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    trackers = sorted(
        [tracker for tracker in snapshot.trackers if tracker.trip_instance_id == trip_instance_id],
        key=tracker_sort_key,
    )
    best_tracker = next(
        (
            tracker
            for tracker in sorted(
                trackers,
                key=lambda item: (
                    item.latest_observed_price is None,
                    item.latest_observed_price or 10**9,
                    *tracker_sort_key(item),
                ),
            )
            if tracker.latest_observed_price is not None
        ),
        None,
    )
    booking = next(
        (
            item
            for item in snapshot.bookings
            if item.trip_instance_id == trip_instance_id and item.status == "active"
        ),
        None,
    )
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
            best_tracker=best_tracker,
            booking=booking,
            observations=observations[:20],
            tracker_label=tracker_label,
            rank_label=rank_label,
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
    if trip is None and len(snapshot.trips) == 1:
        trip = snapshot.trips[0]
    existing = (
        next(
            (
                item
                for item in snapshot.bookings
                if item.trip_instance_id == trip.trip_instance_id and item.status == "active"
            ),
            None,
        )
        if trip is not None
        else None
    )
    trip_trackers = sorted(
        [item for item in snapshot.trackers if trip is not None and item.trip_instance_id == trip.trip_instance_id],
        key=tracker_sort_key,
    )
    best_tracker = next(
        (
            tracker
            for tracker in sorted(
                trip_trackers,
                key=lambda item: (
                    item.latest_observed_price is None,
                    item.latest_observed_price or 10**9,
                    *tracker_sort_key(item),
                ),
            )
            if tracker.latest_observed_price is not None
        ),
        None,
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
            trips=sorted(
                snapshot.trips,
                key=lambda item: (item.outbound_date, item.origin_airport, item.destination_airport),
            ),
            trip_trackers=trip_trackers,
            tracker_choices=[
                {
                    "tracker_id": tracker.tracker_id,
                    "title": rank_label(tracker.detail_rank),
                    "label": tracker_label(tracker),
                    "travel_date": tracker.travel_date,
                    "price": tracker.latest_observed_price,
                }
                for tracker in trip_trackers
            ],
            best_tracker=best_tracker,
            booking_airline_options=SUPPORTED_AIRLINES,
            booking_fare_options=BOOKING_FARE_TYPES,
            tracker_label=tracker_label,
            rank_label=rank_label,
        ),
    )


@router.post("/bookings")
async def save_booking(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    form = await request.form()
    trip_id = str(form.get("trip_instance_id", ""))
    snapshot = load_snapshot(repository, recompute=False)
    trip = next((item for item in snapshot.trips if item.trip_instance_id == trip_id), None)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    tracker_id = str(form.get("tracker_id", "")).strip()
    if tracker_id and not any(
        item.tracker_id == tracker_id
        for item in snapshot.trackers
        if item.trip_instance_id == trip_id
    ):
        raise HTTPException(status_code=400, detail="Tracked option does not belong to this trip")
    bookings, _booking = upsert_booking(snapshot.bookings, trip, form)
    repository.save_bookings(bookings)
    repository.save_trip_instances(snapshot.trips)
    recompute_and_persist(repository)
    return RedirectResponse(url=f"/trips/{trip_id}?message=Booking+saved", status_code=303)
