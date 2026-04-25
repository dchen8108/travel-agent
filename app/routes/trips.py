from __future__ import annotations

import json
from datetime import date
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

from app.models.base import DataScope, FareClass
from app.services.bookings import unlink_bookings_for_trip, unlink_bookings_for_trip_instance
from app.services.data_scope import include_test_data_for_processing
from app.services.dashboard_navigation import trip_focus_url, trip_panel_url
from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.refresh_queue import (
    queue_refresh_for_trip,
    queue_refresh_for_trip_instance,
)
from app.services.snapshot_queries import (
    groups_for_rule,
    instances_for_trip,
    trip_by_id,
)
from app.services.trip_editor import TripSaveInput, save_trip_workflow
from app.services.trip_instances import delete_generated_trip_instance, detach_generated_trip_instance
from app.services.trips import delete_trip, set_trip_active
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import get_repository, redirect_back, redirect_with_message

router = APIRouter(tags=["trips"])


def _parse_route_options(raw: str) -> list[dict[str, object]]:
    payload = json.loads(raw or "[]")
    if not isinstance(payload, list):
        raise ValueError("Route options payload must be a list.")
    route_options: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Route options payload is invalid.")
        route_options.append(
            {
                "route_option_id": str(item.get("route_option_id", "") or ""),
                "savings_needed_vs_previous": int(item.get("savings_needed_vs_previous", 0) or 0),
                "origin_airports": "|".join(item.get("origin_airports", []) or []),
                "destination_airports": "|".join(item.get("destination_airports", []) or []),
                "airlines": "|".join(item.get("airlines", []) or []),
                "stops": str(item.get("stops", "nonstop") or "nonstop"),
                "day_offset": int(item.get("day_offset", 0)),
                "start_time": str(item.get("start_time", "") or ""),
                "end_time": str(item.get("end_time", "") or ""),
                "fare_class": str(item.get("fare_class", item.get("fare_class_policy", FareClass.BASIC_ECONOMY)) or FareClass.BASIC_ECONOMY),
            }
        )
    return route_options


def _parse_trip_group_ids(raw: str, repository: Repository) -> list[str]:
    try:
        payload = json.loads(raw or "[]")
    except ValueError as exc:
        raise ValueError("Collections selection is invalid.") from exc
    if not isinstance(payload, list):
        raise ValueError("Collections selection is invalid.")
    known_group_ids = {group.trip_group_id for group in repository.load_trip_groups()}
    trip_group_ids: list[str] = []
    for item in payload:
        trip_group_id = str(item).strip()
        if not trip_group_id:
            continue
        if trip_group_id not in known_group_ids:
            raise ValueError("Choose valid collections.")
        if trip_group_id not in trip_group_ids:
            trip_group_ids.append(trip_group_id)
    return trip_group_ids


@router.get("/trips")
def trips_index(
    request: Request,
) -> Response:
    query = urlencode(
        [(key, value) for key, value in parse_qsl(request.url.query, keep_blank_values=True) if key != "q"],
        doseq=True,
    )
    redirect_url = f"/?{query}#all-travel" if query else "/#all-travel"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/trips/{trip_id}")
def trip_detail(
    trip_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> Response:
    snapshot = load_persisted_snapshot(repository)
    trip = trip_by_id(snapshot, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.trip_kind == "one_time" and not trip.active:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.trip_kind == "one_time":
        one_time_instances = instances_for_trip(snapshot, trip.trip_id)
        trip_instance_id = one_time_instances[0].trip_instance_id if one_time_instances else None
        return RedirectResponse(
            url=trip_focus_url(snapshot, trip.trip_id, trip_instance_id=trip_instance_id),
            status_code=303,
        )
    return RedirectResponse(url=f"/trips/{trip.trip_id}/edit", status_code=303)


@router.post("/trips")
async def save_trip_action(
    request: Request,
    repository: Repository = Depends(get_repository),
):
    form = await request.form()
    trip_id = str(form.get("trip_id", "")).strip() or None
    existing_trip = next((item for item in repository.load_trips() if item.trip_id == trip_id), None) if trip_id else None
    trip_kind = str(form.get("trip_kind", "weekly"))
    if existing_trip is not None:
        trip_kind = str(existing_trip.trip_kind)
    trip_group_ids_json = str(form.get("trip_group_ids_json", "[]") or "[]")
    preference_mode = str(form.get("preference_mode", "equal")).strip() or "equal"
    source_unmatched_booking_id = str(form.get("source_unmatched_booking_id", "")).strip()
    anchor_date_value = str(form.get("anchor_date", "")).strip()
    anchor_weekday = str(form.get("anchor_weekday", "")).strip()
    route_options_json = str(form.get("route_options_json", "[]"))
    trip_group_ids: list[str] = []
    label = str(form.get("label", "")).strip()
    data_scope = (
        str(form.get("data_scope", existing_trip.data_scope if existing_trip else DataScope.LIVE)).strip()
        or (existing_trip.data_scope if existing_trip else DataScope.LIVE)
    )
    try:
        trip_group_ids = _parse_trip_group_ids(trip_group_ids_json, repository)
        route_options = _parse_route_options(route_options_json)
        result = save_trip_workflow(
            repository,
            data=TripSaveInput(
                trip_id=trip_id,
                label=label,
                trip_kind=trip_kind,
                trip_group_ids=trip_group_ids,
                preference_mode=preference_mode,
                anchor_date=date.fromisoformat(anchor_date_value) if anchor_date_value else None,
                anchor_weekday=anchor_weekday,
                route_options=route_options,
                data_scope=data_scope,
                source_unmatched_booking_id=source_unmatched_booking_id,
            ),
        )
        return redirect_with_message(result.redirect_to, result.message)
    except ValueError as exc:
        return PlainTextResponse(str(exc), status_code=400)


@router.post("/trips/{trip_id}/pause")
def pause_trip_action(
    trip_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    try:
        set_trip_active(repository, trip_id, False)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    sync_and_persist(repository)
    return redirect_back(request, fallback_url="/#all-travel", message="Trip paused")


@router.post("/trips/{trip_id}/activate")
def activate_trip_action(
    trip_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    try:
        trip = next((item for item in repository.load_trips() if item.trip_id == trip_id), None)
        if trip is None:
            raise KeyError("Trip not found")
        if trip.trip_kind == "one_time" and not trip.active:
            raise KeyError("Trip not found")
        set_trip_active(repository, trip_id, True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    snapshot = sync_and_persist(repository)
    queue_refresh_for_trip(
        snapshot,
        repository,
        trip_id=trip_id,
        include_test_data=include_test_data_for_processing(snapshot.app_state),
    )
    return redirect_back(
        request,
        fallback_url="/#all-travel",
        message="Trip activated",
    )


@router.post("/trips/{trip_id}/delete")
def delete_trip_action(
    trip_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    trip = next((item for item in repository.load_trips() if item.trip_id == trip_id), None)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.trip_kind != "one_time":
        raise HTTPException(status_code=400, detail="Only one-time trips can be deleted from the UI.")
    unlinked_bookings = unlink_bookings_for_trip(repository, trip_id=trip.trip_id)
    delete_trip(repository, trip_id)
    sync_and_persist(repository)
    active_unlinked_count = sum(1 for item in unlinked_bookings if item.status == "active")
    message = "Trip deleted"
    if active_unlinked_count == 1:
        message = "Trip deleted. 1 booking needs linking."
    elif active_unlinked_count > 1:
        message = f"Trip deleted. {active_unlinked_count} bookings need linking."
    return redirect_with_message("/#all-travel", message)


@router.post("/trip-instances/{trip_instance_id}/detach")
def detach_trip_instance_action(
    trip_instance_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    try:
        trip_instance = detach_generated_trip_instance(repository, trip_instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        return redirect_back(
            request,
            fallback_url="/#all-travel",
            message=str(exc),
            message_kind="error",
        )
    snapshot = sync_and_persist(repository)
    queue_refresh_for_trip_instance(
        snapshot,
        repository,
        trip_instance_id=trip_instance.trip_instance_id,
        include_test_data=include_test_data_for_processing(snapshot.app_state),
    )
    return redirect_with_message(
        f"/trips/{trip_instance.trip_id}/edit",
        "Trip detached",
    )


@router.post("/trip-instances/{trip_instance_id}/delete-generated")
def delete_generated_trip_instance_action(
    trip_instance_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    snapshot = load_persisted_snapshot(repository)
    existing_instance = next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)
    if existing_instance is None:
        raise HTTPException(status_code=404, detail="Trip instance not found")
    redirect_url = "/#all-travel"
    if existing_instance.recurring_rule_trip_id:
        recurring_rule = trip_by_id(snapshot, existing_instance.recurring_rule_trip_id)
        recurring_rule_groups = groups_for_rule(snapshot, recurring_rule) if recurring_rule else []
        if len(recurring_rule_groups) == 1:
            redirect_url = f"/#group-{recurring_rule_groups[0].trip_group_id}"
    unlinked_bookings = unlink_bookings_for_trip_instance(repository, trip_instance_id=trip_instance_id)
    try:
        delete_generated_trip_instance(repository, trip_instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        return redirect_back(
            request,
            fallback_url="/#all-travel",
            message=str(exc),
            message_kind="error",
        )
    sync_and_persist(repository)
    active_unlinked_count = sum(1 for item in unlinked_bookings if item.status == "active")
    message = "Trip deleted"
    if active_unlinked_count == 1:
        message = "Trip deleted. 1 booking needs linking."
    elif active_unlinked_count > 1:
        message = f"Trip deleted. {active_unlinked_count} bookings need linking."
    return redirect_with_message(redirect_url, message)
