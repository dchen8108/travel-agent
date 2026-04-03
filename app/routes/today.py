from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.services.dashboard import (
    active_booking_count_for_instance,
    best_tracker,
    booking_for_instance,
    load_snapshot,
    rebook_savings,
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
    planned_instances = [
        instance
        for instance in snapshot.trip_instances
        if instance.anchor_date >= today
        and not instance.deleted
        and active_booking_count_for_instance(snapshot, instance.trip_instance_id) == 0
    ]
    booked_instances = [
        instance
        for instance in snapshot.trip_instances
        if instance.anchor_date >= today
        and not instance.deleted
        and active_booking_count_for_instance(snapshot, instance.trip_instance_id) > 0
    ]
    planned_instances.sort(key=lambda item: (item.anchor_date, item.display_label.lower()))
    booked_instances.sort(key=lambda item: (item.anchor_date, item.display_label.lower()))

    action_booked_instances = [
        instance for instance in booked_instances if rebook_savings(snapshot, instance.trip_instance_id) is not None
    ]
    monitoring_instances = [
        instance for instance in booked_instances if rebook_savings(snapshot, instance.trip_instance_id) is None
    ]
    action_count = len(open_unmatched) + len(action_booked_instances)
    planned_preview = planned_instances[:8]
    monitoring_preview = monitoring_instances[:8]

    return get_templates(request).TemplateResponse(
        request=request,
        name="today.html",
        context=base_context(
            request,
            page="today",
            snapshot=snapshot,
            open_unmatched=open_unmatched,
            action_booked_instances=action_booked_instances,
            planned_instances=planned_instances,
            planned_preview=planned_preview,
            monitoring_instances=monitoring_instances,
            monitoring_preview=monitoring_preview,
            action_count=action_count,
            total_booked_monitoring=len(booked_instances),
            booking_for_instance=booking_for_instance,
            best_tracker=best_tracker,
            trip_for_instance=trip_for_instance,
            trip_focus_url=trip_focus_url,
        ),
    )
