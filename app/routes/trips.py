from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.catalog import catalogs_json
from app.models.base import TravelState
from app.route_options import day_offset_label, route_option_summary
from app.services.dashboard import (
    best_tracker,
    booking_for_instance,
    instances_for_trip,
    load_snapshot,
    route_options_for_trip,
    trackers_for_instance,
)
from app.services.trips import delete_trip, save_trip, set_trip_active
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(tags=["trips"])


def _trip_form_state(trip, route_options):
    if trip is None:
        return {
            "trip_id": "",
            "label": "",
            "trip_kind": "weekly",
            "anchor_date": "",
            "anchor_weekday": "Monday",
        }
    return {
        "trip_id": trip.trip_id,
        "label": trip.label,
        "trip_kind": trip.trip_kind,
        "anchor_date": trip.anchor_date.isoformat() if trip.anchor_date else "",
        "anchor_weekday": trip.anchor_weekday or "Monday",
        "created_at": trip.created_at.isoformat(),
    }


def _route_option_state(route_options):
    return [
        {
            "route_option_id": option.route_option_id,
            "origin_airports": option.origin_codes,
            "destination_airports": option.destination_codes,
            "airlines": option.airline_codes,
            "day_offset": option.day_offset,
            "start_time": option.start_time,
            "end_time": option.end_time,
        }
        for option in route_options
    ]


def _route_option_state_from_payloads(payloads: list[dict[str, object]]):
    def _as_list(value: object) -> list[str]:
        if isinstance(value, str):
            return [item for item in value.split("|") if item]
        return list(value or [])

    return [
        {
            "route_option_id": str(item.get("route_option_id", "") or ""),
            "origin_airports": _as_list(item.get("origin_airports")),
            "destination_airports": _as_list(item.get("destination_airports")),
            "airlines": _as_list(item.get("airlines")),
            "day_offset": int(item.get("day_offset", 0)),
            "start_time": str(item.get("start_time", "") or ""),
            "end_time": str(item.get("end_time", "") or ""),
        }
        for item in payloads
    ]


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
                "origin_airports": "|".join(item.get("origin_airports", []) or []),
                "destination_airports": "|".join(item.get("destination_airports", []) or []),
                "airlines": "|".join(item.get("airlines", []) or []),
                "day_offset": int(item.get("day_offset", 0)),
                "start_time": str(item.get("start_time", "") or ""),
                "end_time": str(item.get("end_time", "") or ""),
            }
        )
    return route_options


@router.get("/trips", response_class=HTMLResponse)
def trips_index(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    return get_templates(request).TemplateResponse(
        request=request,
        name="trips.html",
        context=base_context(
            request,
            page="trips",
            snapshot=snapshot,
            instances_for_trip=instances_for_trip,
            route_options_for_trip=route_options_for_trip,
        ),
    )


@router.get("/trips/new", response_class=HTMLResponse)
def new_trip(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    return get_templates(request).TemplateResponse(
        request=request,
        name="trip_form.html",
        context=base_context(
            request,
            page="trips",
            snapshot=snapshot,
            trip=None,
            route_options=[],
            trip_form_state=_trip_form_state(None, []),
            route_option_state=_route_option_state([]),
            catalogs_json=catalogs_json(),
        ),
    )


@router.get("/trips/{trip_id}", response_class=HTMLResponse)
def trip_detail(
    trip_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    trip = next((item for item in snapshot.trips if item.trip_id == trip_id), None)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    route_options = route_options_for_trip(snapshot, trip.trip_id)
    trip_instances = instances_for_trip(snapshot, trip.trip_id)
    return get_templates(request).TemplateResponse(
        request=request,
        name="trip_detail.html",
        context=base_context(
            request,
            page="trips",
            snapshot=snapshot,
            trip=trip,
            route_options=route_options,
            trip_instances=trip_instances,
            trackers_for_instance=trackers_for_instance,
            booking_for_instance=booking_for_instance,
            best_tracker=best_tracker,
            day_offset_label=day_offset_label,
            route_option_summary=route_option_summary,
        ),
    )


@router.get("/trips/{trip_id}/edit", response_class=HTMLResponse)
def edit_trip(
    trip_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    trip = next((item for item in snapshot.trips if item.trip_id == trip_id), None)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    route_options = route_options_for_trip(snapshot, trip.trip_id)
    return get_templates(request).TemplateResponse(
        request=request,
        name="trip_form.html",
        context=base_context(
            request,
            page="trips",
            snapshot=snapshot,
            trip=trip,
            route_options=route_options,
            trip_form_state=_trip_form_state(trip, route_options),
            route_option_state=_route_option_state(route_options),
            catalogs_json=catalogs_json(),
        ),
    )


@router.post("/trips")
async def save_trip_action(
    request: Request,
    repository: Repository = Depends(get_repository),
):
    form = await request.form()
    trip_id = str(form.get("trip_id", "")).strip() or None
    existing_trip = next((item for item in repository.load_trips() if item.trip_id == trip_id), None) if trip_id else None
    trip_kind = str(form.get("trip_kind", "weekly"))
    anchor_date_value = str(form.get("anchor_date", "")).strip()
    anchor_weekday = str(form.get("anchor_weekday", "")).strip()
    route_options_json = str(form.get("route_options_json", "[]"))
    raw_route_option_state: list[dict[str, object]]
    try:
        raw_route_option_state = json.loads(route_options_json or "[]")
    except ValueError:
        raw_route_option_state = []
    try:
        route_options = _parse_route_options(route_options_json)
        trip = save_trip(
            repository,
            trip_id=trip_id,
            label=str(form.get("label", "")).strip(),
            trip_kind=trip_kind,
            active=existing_trip.active if existing_trip else True,
            anchor_date=date.fromisoformat(anchor_date_value) if anchor_date_value else None,
            anchor_weekday=anchor_weekday,
            route_option_payloads=route_options,
        )
        sync_and_persist(repository)
        return RedirectResponse(url=f"/trips/{trip.trip_id}?message=Trip+saved", status_code=303)
    except ValueError as exc:
        snapshot = load_snapshot(repository)
        return get_templates(request).TemplateResponse(
            request=request,
            name="trip_form.html",
            context=base_context(
                request,
                page="trips",
                snapshot=snapshot,
                trip=None,
                route_options=[],
                error_message=str(exc),
                trip_form_state={
                    "trip_id": trip_id or "",
                    "label": str(form.get("label", "")).strip(),
                    "trip_kind": trip_kind,
                    "anchor_date": anchor_date_value,
                    "anchor_weekday": anchor_weekday or "Monday",
                },
                route_option_state=_route_option_state_from_payloads(raw_route_option_state),
                catalogs_json=catalogs_json(),
            ),
            status_code=400,
        )


@router.post("/trips/{trip_id}/pause")
def pause_trip_action(
    trip_id: str,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    try:
        set_trip_active(repository, trip_id, False)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    sync_and_persist(repository)
    return RedirectResponse(url="/trips?message=Trip+paused", status_code=303)


@router.post("/trips/{trip_id}/activate")
def activate_trip_action(
    trip_id: str,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    try:
        set_trip_active(repository, trip_id, True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    sync_and_persist(repository)
    return RedirectResponse(url=f"/trips/{trip_id}?message=Trip+activated", status_code=303)


@router.post("/trips/{trip_id}/delete")
def delete_trip_action(
    trip_id: str,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    delete_trip(repository, trip_id)
    sync_and_persist(repository)
    return RedirectResponse(url="/trips?message=Trip+deleted", status_code=303)


@router.post("/trip-instances/{trip_instance_id}/skip")
def skip_trip_instance(
    trip_instance_id: str,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    trip_instances = repository.load_trip_instances()
    booking = next(
        (
            item
            for item in repository.load_bookings()
            if item.trip_instance_id == trip_instance_id and item.status == "active"
        ),
        None,
    )
    if booking is not None:
        raise HTTPException(status_code=400, detail="Cannot skip an occurrence with an active booking.")
    trip_instance = next((item for item in trip_instances if item.trip_instance_id == trip_instance_id), None)
    if trip_instance is None:
        raise HTTPException(status_code=404, detail="Trip instance not found")
    trip_instance.travel_state = TravelState.SKIPPED
    repository.save_trip_instances(trip_instances)
    sync_and_persist(repository)
    return RedirectResponse(url=f"/trips/{trip_instance.trip_id}?message=Occurrence+skipped", status_code=303)


@router.post("/trip-instances/{trip_instance_id}/restore")
def restore_trip_instance(
    trip_instance_id: str,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    trip_instances = repository.load_trip_instances()
    trip_instance = next((item for item in trip_instances if item.trip_instance_id == trip_instance_id), None)
    if trip_instance is None:
        raise HTTPException(status_code=404, detail="Trip instance not found")
    trip_instance.travel_state = TravelState.OPEN
    repository.save_trip_instances(trip_instances)
    sync_and_persist(repository)
    return RedirectResponse(url=f"/trips/{trip_instance.trip_id}?message=Occurrence+restored", status_code=303)
