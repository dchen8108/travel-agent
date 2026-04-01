from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.models.base import RecommendationState, TravelState
from app.services.dashboard import (
    best_tracker,
    booking_for_instance,
    load_snapshot,
    trip_for_instance,
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
    today = date.today()
    open_unmatched = [item for item in snapshot.unmatched_bookings if item.resolution_status == "open"]
    open_instances = [
        instance
        for instance in snapshot.trip_instances
        if instance.anchor_date >= today
        and instance.travel_state == TravelState.OPEN
    ]
    booked_instances = [
        instance
        for instance in snapshot.trip_instances
        if instance.anchor_date >= today and instance.travel_state == TravelState.BOOKED
    ]
    open_instances.sort(key=lambda item: (item.anchor_date, item.display_label.lower()))
    booked_instances.sort(key=lambda item: (item.anchor_date, item.display_label.lower()))

    action_open_instances = [
        instance for instance in open_instances if instance.recommendation_state == RecommendationState.BOOK_NOW
    ]
    action_booked_instances = [
        instance for instance in booked_instances if instance.recommendation_state == RecommendationState.REBOOK
    ]
    watching_instances = [
        instance for instance in open_instances if instance.recommendation_state != RecommendationState.BOOK_NOW
    ]
    monitoring_instances = [
        instance for instance in booked_instances if instance.recommendation_state != RecommendationState.REBOOK
    ]
    action_count = len(open_unmatched) + len(action_open_instances) + len(action_booked_instances)
    total_booked_monitoring = len(booked_instances)
    watching_preview = watching_instances[:8]
    monitoring_preview = monitoring_instances[:6]

    return get_templates(request).TemplateResponse(
        request=request,
        name="today.html",
        context=base_context(
            request,
            page="today",
            snapshot=snapshot,
            open_unmatched=open_unmatched,
            action_open_instances=action_open_instances,
            action_booked_instances=action_booked_instances,
            watching_instances=watching_instances,
            watching_preview=watching_preview,
            monitoring_instances=monitoring_instances,
            monitoring_preview=monitoring_preview,
            action_count=action_count,
            total_booked_monitoring=total_booked_monitoring,
            booking_for_instance=booking_for_instance,
            best_tracker=best_tracker,
            trip_for_instance=trip_for_instance,
            trip_focus_url=trip_focus_url,
        ),
    )
