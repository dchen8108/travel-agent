from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.catalog import catalogs_json
from app.models.base import BookingStatus, DataScope, FareClassPolicy
from app.route_options import day_offset_label
from app.services.bookings import (
    BookingCandidate,
    resolve_unmatched_booking_to_trip,
    suggested_route_option_payload_for_booking,
    unlink_bookings_for_trip,
    unlink_bookings_for_trip_instance,
)
from app.services.data_scope import include_test_data_for_processing
from app.services.dashboard_navigation import trip_focus_url, trip_panel_url
from app.services.dashboard_booking_views import (
    booking_reference_label,
    default_trip_label_for_booking,
)
from app.services.dashboard_queries import trip_groups
from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.scheduled_trip_state import (
    active_booking_count_for_instance,
)
from app.services.group_memberships import replace_manual_trip_instance_groups
from app.services.groups import find_or_create_trip_group
from app.services.refresh_queue import (
    queued_refresh_message,
    queue_refresh_for_trip,
    queue_refresh_for_trip_instance,
)
from app.services.snapshot_queries import (
    groups_for_rule,
    groups_for_trip,
    instances_for_rule,
    instances_for_trip,
    recurring_rule_for_instance,
    route_options_for_trip,
    trip_by_id,
    trip_for_instance,
)
from app.services.trip_instances import delete_generated_trip_instance, detach_generated_trip_instance
from app.services.trips import delete_trip, save_trip, set_trip_active
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import back_url, base_context, get_repository, get_templates, redirect_back, redirect_with_message

router = APIRouter(tags=["trips"])


def _trip_form_state(trip, route_options, *, trip_group_ids=None):
    if trip is None:
        return {
            "trip_id": "",
            "label": "",
            "trip_kind": "one_time",
            "trip_group_ids": [],
            "preference_mode": "equal",
            "anchor_date": "",
            "anchor_weekday": "Monday",
            "data_scope": DataScope.LIVE,
        }
    return {
        "trip_id": trip.trip_id,
        "label": trip.label,
        "trip_kind": trip.trip_kind,
        "trip_group_ids": trip_group_ids or [],
        "preference_mode": trip.preference_mode,
        "anchor_date": trip.anchor_date.isoformat() if trip.anchor_date else "",
        "anchor_weekday": trip.anchor_weekday or "Monday",
        "data_scope": trip.data_scope,
        "created_at": trip.created_at.isoformat(),
    }


def _route_option_state(route_options):
    return [
        {
            "route_option_id": option.route_option_id,
            "savings_needed_vs_previous": option.savings_needed_vs_previous,
            "origin_airports": option.origin_codes,
            "destination_airports": option.destination_codes,
            "airlines": option.airline_codes,
            "day_offset": option.day_offset,
            "start_time": option.start_time,
            "end_time": option.end_time,
            "fare_class_policy": option.fare_class_policy,
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
            "savings_needed_vs_previous": int(item.get("savings_needed_vs_previous", 0) or 0),
            "origin_airports": _as_list(item.get("origin_airports")),
            "destination_airports": _as_list(item.get("destination_airports")),
            "airlines": _as_list(item.get("airlines")),
            "day_offset": int(item.get("day_offset", 0)),
            "start_time": str(item.get("start_time", "") or ""),
            "end_time": str(item.get("end_time", "") or ""),
            "fare_class_policy": str(item.get("fare_class_policy", FareClassPolicy.INCLUDE_BASIC) or FareClassPolicy.INCLUDE_BASIC),
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
                "savings_needed_vs_previous": int(item.get("savings_needed_vs_previous", 0) or 0),
                "origin_airports": "|".join(item.get("origin_airports", []) or []),
                "destination_airports": "|".join(item.get("destination_airports", []) or []),
                "airlines": "|".join(item.get("airlines", []) or []),
                "day_offset": int(item.get("day_offset", 0)),
                "start_time": str(item.get("start_time", "") or ""),
                "end_time": str(item.get("end_time", "") or ""),
                "fare_class_policy": str(item.get("fare_class_policy", FareClassPolicy.INCLUDE_BASIC) or FareClassPolicy.INCLUDE_BASIC),
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


def _recurring_linked_trip_count(snapshot, trip) -> int:
    if trip.trip_kind != "weekly":
        return 0
    return sum(
        1
        for instance in instances_for_rule(snapshot, trip.trip_id)
        if not instance.deleted and instance.inheritance_mode == "attached"
    )


def _trip_edit_cancel_url(request: Request, snapshot, trip) -> str:
    if trip.trip_kind == "weekly":
        recurring_groups = groups_for_rule(snapshot, trip)
        if len(recurring_groups) == 1:
            fallback_url = f"/#group-{recurring_groups[0].trip_group_id}"
        else:
            fallback_url = "/#all-travel"
        return back_url(request, fallback_url=fallback_url)
    one_time_instances = [
        instance
        for instance in instances_for_trip(snapshot, trip.trip_id)
        if not instance.deleted
    ]
    fallback_url = (
        trip_focus_url(snapshot, trip.trip_id, trip_instance_id=one_time_instances[0].trip_instance_id)
        if one_time_instances
        else "/#all-travel"
    )
    return back_url(request, fallback_url=fallback_url)


def _render_trip_form(
    request: Request,
    *,
    snapshot,
    trip,
    route_options,
    trip_form_state,
    route_option_state,
    source_unmatched_booking=None,
    cancel_url: str,
    recurring_edit_warning: dict[str, object] | None = None,
    detachable_trip_instance_id: str = "",
    error_message: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return get_templates(request).TemplateResponse(
        request=request,
        name="trip_form.html",
        context=base_context(
            request,
            page="trips",
            snapshot=snapshot,
            trip=trip,
            route_options=route_options,
            error_message=error_message or "",
            trip_form_state=trip_form_state,
            route_option_state=route_option_state,
            source_unmatched_booking=source_unmatched_booking,
            cancel_url=cancel_url,
            recurring_edit_warning=recurring_edit_warning,
            detachable_trip_instance_id=detachable_trip_instance_id,
            source_booking_reference_label=(
                booking_reference_label(source_unmatched_booking)
                if source_unmatched_booking is not None
                else ""
            ),
            trip_groups=trip_groups(snapshot),
            trip_group_picker_options=[
                {"value": group.trip_group_id, "label": group.label}
                for group in trip_groups(snapshot)
            ],
            catalogs_json=catalogs_json(),
        ),
        status_code=status_code,
    )


def _linked_booking_route_warning_count(snapshot, trip) -> int:
    if trip.trip_kind == "weekly":
        trip_instance_ids = {
            instance.trip_instance_id
            for instance in instances_for_rule(snapshot, trip.trip_id)
            if not instance.deleted
        }
    else:
        trip_instance_ids = {
            instance.trip_instance_id
            for instance in instances_for_trip(snapshot, trip.trip_id)
            if not instance.deleted
        }
    return sum(
        1
        for booking in snapshot.bookings
        if booking.status == BookingStatus.ACTIVE
        and booking.trip_instance_id in trip_instance_ids
        and not booking.route_option_id
    )


@router.get("/trips", response_class=HTMLResponse)
def trips_index(
    request: Request,
) -> Response:
    query = request.url.query
    redirect_url = f"/?{query}#all-travel" if query else "/#all-travel"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/trips/new", response_class=HTMLResponse)
def new_trip(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_persisted_snapshot(repository)
    trip_kind = str(request.query_params.get("trip_kind", "one_time")).strip() or "one_time"
    trip_group_id = str(request.query_params.get("trip_group_id", "")).strip()
    unmatched_booking_id = str(request.query_params.get("unmatched_booking_id", "")).strip()
    trip_label = str(request.query_params.get("trip_label", "")).strip()
    source_unmatched_booking = next(
        (
            item
            for item in snapshot.unmatched_bookings
            if item.unmatched_booking_id == unmatched_booking_id and item.resolution_status == "open"
        ),
        None,
    ) if unmatched_booking_id else None
    if unmatched_booking_id and source_unmatched_booking is None:
        raise HTTPException(status_code=404, detail="Unmatched booking not found")
    trip_form_state = {
        **_trip_form_state(None, []),
        "trip_kind": trip_kind if trip_kind in {"one_time", "weekly"} else "one_time",
        "trip_group_ids": [trip_group_id] if trip_group_id else [],
    }
    route_option_state = _route_option_state([])
    if source_unmatched_booking is not None:
        candidate = BookingCandidate(
            airline=source_unmatched_booking.airline,
            origin_airport=source_unmatched_booking.origin_airport,
            destination_airport=source_unmatched_booking.destination_airport,
            departure_date=source_unmatched_booking.departure_date,
            departure_time=source_unmatched_booking.departure_time,
            arrival_time=source_unmatched_booking.arrival_time,
            booked_price=source_unmatched_booking.booked_price,
            record_locator=source_unmatched_booking.record_locator,
        )
        suggested_label = trip_label or default_trip_label_for_booking(source_unmatched_booking)
        trip_form_state.update(
            {
                "label": suggested_label,
                "trip_kind": "one_time",
                "anchor_date": source_unmatched_booking.departure_date.isoformat(),
                "data_scope": source_unmatched_booking.data_scope,
            }
        )
        route_option_state = _route_option_state_from_payloads(
            [suggested_route_option_payload_for_booking(candidate)]
        )
    return _render_trip_form(
        request,
        snapshot=snapshot,
        trip=None,
        route_options=[],
        trip_form_state=trip_form_state,
        route_option_state=route_option_state,
        source_unmatched_booking=source_unmatched_booking,
        cancel_url=back_url(
            request,
            fallback_url=(
                f"/#group-{trip_group_id}"
                if trip_group_id
                else "/#needs-linking" if source_unmatched_booking is not None else "/"
            ),
        ),
    )


@router.get("/trips/{trip_id}", response_class=HTMLResponse)
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


@router.get("/trips/{trip_id}/edit", response_class=HTMLResponse)
def edit_trip(
    trip_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
    trip_instance_id: str | None = None,
) -> HTMLResponse:
    snapshot = load_persisted_snapshot(repository)
    trip = next((item for item in snapshot.trips if item.trip_id == trip_id), None)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.trip_kind == "one_time" and not trip.active:
        raise HTTPException(status_code=404, detail="Trip not found")
    route_options = route_options_for_trip(snapshot, trip.trip_id)
    recurring_edit_warning = None
    detachable_trip_instance_id = ""
    if trip.trip_kind == "weekly":
        linked_trip_count = _recurring_linked_trip_count(snapshot, trip)
        recurring_edit_warning = {
            "linked_trip_count": linked_trip_count,
            "linked_trip_label": "linked trip" if linked_trip_count == 1 else "linked trips",
        }
        if trip_instance_id:
            matching_instance = next(
                (
                    instance
                    for instance in instances_for_rule(snapshot, trip.trip_id)
                    if instance.trip_instance_id == trip_instance_id
                    and not instance.deleted
                    and instance.inheritance_mode == "attached"
                ),
                None,
            )
            detachable_trip_instance_id = matching_instance.trip_instance_id if matching_instance else ""
    return _render_trip_form(
        request,
        snapshot=snapshot,
        trip=trip,
        route_options=route_options,
        trip_form_state=_trip_form_state(
            trip,
            route_options,
            trip_group_ids=[group.trip_group_id for group in groups_for_trip(snapshot, trip)],
        ),
        route_option_state=_route_option_state(route_options),
        cancel_url=_trip_edit_cancel_url(request, snapshot, trip),
        recurring_edit_warning=recurring_edit_warning,
        detachable_trip_instance_id=detachable_trip_instance_id,
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
    if existing_trip is not None:
        trip_kind = str(existing_trip.trip_kind)
    trip_group_ids_json = str(form.get("trip_group_ids_json", "[]") or "[]")
    preference_mode = str(form.get("preference_mode", "equal")).strip() or "equal"
    source_unmatched_booking_id = str(form.get("source_unmatched_booking_id", "")).strip()
    detachable_trip_instance_id = str(form.get("detachable_trip_instance_id", "")).strip()
    cancel_url = str(form.get("cancel_url", "")).strip()
    anchor_date_value = str(form.get("anchor_date", "")).strip()
    anchor_weekday = str(form.get("anchor_weekday", "")).strip()
    route_options_json = str(form.get("route_options_json", "[]"))
    trip_group_ids: list[str] = []
    label = str(form.get("label", "")).strip()
    data_scope = (
        str(form.get("data_scope", existing_trip.data_scope if existing_trip else DataScope.LIVE)).strip()
        or (existing_trip.data_scope if existing_trip else DataScope.LIVE)
    )
    raw_route_option_state: list[dict[str, object]]
    try:
        raw_route_option_state = json.loads(route_options_json or "[]")
    except ValueError:
        raw_route_option_state = []
    try:
        trip_group_ids = _parse_trip_group_ids(trip_group_ids_json, repository)
        route_options = _parse_route_options(route_options_json)
        auto_created_group = False
        if trip_kind == "weekly" and not trip_group_ids:
            existing_rule_has_groups = bool(
                existing_trip
                and any(target.rule_trip_id == existing_trip.trip_id for target in repository.load_rule_group_targets())
            )
            if existing_trip is not None and existing_rule_has_groups:
                raise ValueError("Recurring rules must stay in at least one group.")
            if not label:
                raise ValueError("Trip label is required.")
            with repository.transaction():
                fallback_group = find_or_create_trip_group(
                    repository,
                    label=label,
                    data_scope=data_scope,
                )
                trip_group_ids = [fallback_group.trip_group_id]
                trip = save_trip(
                    repository,
                    trip_id=trip_id,
                    label=label,
                    trip_kind=trip_kind,
                    preference_mode=preference_mode,
                    active=existing_trip.active if existing_trip else True,
                    anchor_date=date.fromisoformat(anchor_date_value) if anchor_date_value else None,
                    anchor_weekday=anchor_weekday,
                    trip_group_ids=trip_group_ids,
                    route_option_payloads=route_options,
                    data_scope=data_scope,
                )
                auto_created_group = True
        if not auto_created_group:
            trip = save_trip(
                repository,
                trip_id=trip_id,
                label=label,
                trip_kind=trip_kind,
                preference_mode=preference_mode,
                active=existing_trip.active if existing_trip else True,
                anchor_date=date.fromisoformat(anchor_date_value) if anchor_date_value else None,
                anchor_weekday=anchor_weekday,
                trip_group_ids=trip_group_ids,
                route_option_payloads=route_options,
                data_scope=data_scope,
            )
        snapshot = sync_and_persist(repository)
        if trip.trip_kind == "one_time":
            replace_manual_trip_instance_groups(
                repository,
                trip_instance_ids=[
                    instance.trip_instance_id
                    for instance in snapshot.trip_instances
                    if instance.trip_id == trip.trip_id and not instance.deleted
                ],
                trip_group_ids=trip_group_ids,
                data_scope=trip.data_scope,
            )
            snapshot = load_persisted_snapshot(repository)
        linked_booking = None
        if source_unmatched_booking_id:
            linked_booking = resolve_unmatched_booking_to_trip(
                repository,
                unmatched_booking_id=source_unmatched_booking_id,
                trip_id=trip.trip_id,
            )
            if linked_booking is not None:
                snapshot = sync_and_persist(repository)
            else:
                snapshot = load_persisted_snapshot(repository)
        queued_count = queue_refresh_for_trip(
            snapshot,
            repository,
            trip_id=trip.trip_id,
            include_test_data=include_test_data_for_processing(snapshot.app_state),
        )
        message = queued_refresh_message(
            "Trip created from booking" if source_unmatched_booking_id else "Trip saved",
            queued_count,
        )
        warning_count = _linked_booking_route_warning_count(snapshot, trip)
        if warning_count:
            booking_noun = "booking" if warning_count == 1 else "bookings"
            verb = "does" if warning_count == 1 else "do"
            message = (
                f"{message} {warning_count} linked {booking_noun} "
                f"{verb} not match a unique tracked route."
            )
        if source_unmatched_booking_id and linked_booking is None:
            message = f"{message} Booking still needs linking."
            return redirect_with_message("/#needs-linking", message)
        if linked_booking is not None:
            return redirect_with_message(
                trip_panel_url(
                    snapshot,
                    trip.trip_id,
                    trip_instance_id=linked_booking.trip_instance_id,
                    panel="bookings",
                ),
                message,
            )
        if trip.trip_kind == "one_time":
            active_instances = [
                instance
                for instance in instances_for_trip(snapshot, trip.trip_id)
                if not instance.deleted
            ]
            if active_instances:
                return redirect_with_message(
                    trip_focus_url(snapshot, trip.trip_id, trip_instance_id=active_instances[0].trip_instance_id),
                    message,
                )
        recurring_groups = groups_for_trip(snapshot, trip)
        if len(recurring_groups) == 1:
            return redirect_with_message(f"/#group-{recurring_groups[0].trip_group_id}", message)
        return redirect_with_message("/#all-travel", message)
    except ValueError as exc:
        snapshot = load_persisted_snapshot(repository)
        source_unmatched_booking = next(
            (
                item
                for item in snapshot.unmatched_bookings
            if item.unmatched_booking_id == source_unmatched_booking_id and item.resolution_status == "open"
            ),
            None,
        ) if source_unmatched_booking_id else None
        recurring_edit_warning = None
        if existing_trip and existing_trip.trip_kind == "weekly":
            linked_trip_count = _recurring_linked_trip_count(snapshot, existing_trip)
            recurring_edit_warning = {
                "linked_trip_count": linked_trip_count,
                "linked_trip_label": "linked trip" if linked_trip_count == 1 else "linked trips",
            }
        return _render_trip_form(
            request,
            snapshot=snapshot,
            trip=existing_trip,
            route_options=[],
            error_message=str(exc),
            trip_form_state={
                "trip_id": trip_id or "",
                "label": label,
                "trip_kind": str(existing_trip.trip_kind) if existing_trip else trip_kind,
                "trip_group_ids": trip_group_ids,
                "preference_mode": preference_mode,
                "anchor_date": anchor_date_value,
                "anchor_weekday": anchor_weekday or "Monday",
                "data_scope": data_scope,
            },
            route_option_state=_route_option_state_from_payloads(raw_route_option_state),
            source_unmatched_booking=source_unmatched_booking,
            recurring_edit_warning=recurring_edit_warning,
            detachable_trip_instance_id=detachable_trip_instance_id,
            cancel_url=cancel_url or (
                _trip_edit_cancel_url(request, snapshot, existing_trip) if existing_trip else (
                    "/#needs-linking" if source_unmatched_booking is not None else "/"
                )
            ),
            status_code=400,
        )


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
    queued_count = queue_refresh_for_trip(
        snapshot,
        repository,
        trip_id=trip_id,
        include_test_data=include_test_data_for_processing(snapshot.app_state),
    )
    return redirect_back(
        request,
        fallback_url="/#all-travel",
        message=queued_refresh_message("Trip activated", queued_count),
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
    queued_count = queue_refresh_for_trip_instance(
        snapshot,
        repository,
        trip_instance_id=trip_instance.trip_instance_id,
        include_test_data=include_test_data_for_processing(snapshot.app_state),
    )
    return redirect_with_message(
        f"/trips/{trip_instance.trip_id}/edit",
        queued_refresh_message("Trip detached", queued_count),
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
