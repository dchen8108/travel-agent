from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.models.base import RecommendationState, TravelState
from app.services.dashboard import (
    best_tracker,
    booking_for_instance,
    instances_for_trip,
    load_snapshot,
    route_options_for_trip,
    trackers_for_instance,
    trip_focus_url,
)
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(tags=["today"])


@router.get("/", response_class=HTMLResponse)
def today(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    open_unmatched = [item for item in snapshot.unmatched_bookings if item.resolution_status == "open"]
    setup_instances = [
        instance
        for instance in snapshot.trip_instances
        if instance.travel_state == TravelState.OPEN
        and instance.recommendation_state == RecommendationState.NEEDS_TRACKER_SETUP
    ]
    open_instances = [
        instance
        for instance in snapshot.trip_instances
        if instance.travel_state == TravelState.OPEN
        and instance.recommendation_state in {RecommendationState.WAIT, RecommendationState.BOOK_NOW}
    ]
    booked_instances = [
        instance
        for instance in snapshot.trip_instances
        if instance.travel_state == TravelState.BOOKED
    ]

    return get_templates(request).TemplateResponse(
        request=request,
        name="today.html",
        context=base_context(
            request,
            page="today",
            snapshot=snapshot,
            open_unmatched=open_unmatched,
            setup_instances=setup_instances,
            open_instances=open_instances,
            booked_instances=booked_instances,
            booking_for_instance=booking_for_instance,
            best_tracker=best_tracker,
            trackers_for_instance=trackers_for_instance,
            route_options_for_trip=route_options_for_trip,
            instances_for_trip=instances_for_trip,
            trip_focus_url=trip_focus_url,
        ),
    )
