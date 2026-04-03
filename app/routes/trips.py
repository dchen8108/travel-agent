from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.catalog import catalogs_json
from app.models.base import BookingStatus, DataScope, FareClassPolicy
from app.services.data_scope import include_test_data_for_processing
from app.services.dashboard import (
    active_booking_count_for_instance,
    best_tracker,
    booking_for_instance,
    group_for_instance,
    group_for_trip,
    groups_for_instance,
    groups_for_trip,
    groups_for_rule,
    horizon_instances_for_rule,
    horizon_instances_for_trip,
    instances_for_rule,
    instances_for_trip,
    load_snapshot,
    recurring_rules_for_group,
    route_options_for_trip,
    scheduled_instances,
    trip_groups,
    trip_by_id,
    trackers_for_instance,
    trip_for_instance,
    trip_focus_url,
    recurring_rule_for_instance,
)
from app.services.group_memberships import replace_manual_trip_instance_groups
from app.services.groups import find_or_create_trip_group
from app.services.refresh_queue import (
    queued_refresh_message,
    queue_refresh_for_trip,
    queue_refresh_for_trip_instance,
)
from app.services.trip_instances import delete_generated_trip_instance, detach_generated_trip_instance
from app.services.trips import delete_trip, save_trip, set_trip_active
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates, redirect_back, redirect_with_message

router = APIRouter(tags=["trips"])


def _trip_form_state(trip, route_options, *, trip_group_ids=None):
    if trip is None:
        return {
            "trip_id": "",
            "label": "",
            "trip_kind": "weekly",
            "trip_group_ids": [],
            "preference_mode": "equal",
            "anchor_date": "",
            "anchor_weekday": "Monday",
        }
    return {
        "trip_id": trip.trip_id,
        "label": trip.label,
        "trip_kind": trip.trip_kind,
        "trip_group_ids": trip_group_ids or [],
        "preference_mode": trip.preference_mode,
        "anchor_date": trip.anchor_date.isoformat() if trip.anchor_date else "",
        "anchor_weekday": trip.anchor_weekday or "Monday",
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


def _route_option_views(trip, route_options):
    cumulative_bias = 0
    views = []
    bias_enabled = getattr(trip, "preference_mode", "equal") == "ranked_bias"
    for option in route_options:
        pairwise_bias = option.savings_needed_vs_previous if bias_enabled else 0
        cumulative_bias += pairwise_bias
        if not bias_enabled:
            preference_note = "Treated equally with the other route options."
        elif option.rank == 1:
            preference_note = "Highest preference. Lower options need extra savings to outrank it."
        else:
            preference_note = f"Needs at least ${pairwise_bias} savings versus option {option.rank - 1}."
        views.append(
            {
                "option": option,
                "pairwise_bias": pairwise_bias,
                "cumulative_bias": cumulative_bias if bias_enabled else 0,
                "preference_note": preference_note,
            }
        )
    return views


def _scheduled_view_state(snapshot, request: Request) -> dict[str, object]:
    today = date.today()
    group_items = trip_groups(snapshot)
    group_ids = {group.trip_group_id for group in group_items}
    selected_trip_group_ids = [
        group.trip_group_id
        for group in group_items
        if group.trip_group_id in request.query_params.getlist("trip_group_id") and group.trip_group_id in group_ids
    ]
    selected_trip_group_id_set = set(selected_trip_group_ids)
    search_query = str(request.query_params.get("q", "")).strip()

    scheduled_items = scheduled_instances(
        snapshot,
        trip_group_ids=selected_trip_group_id_set or None,
        today=today,
    )
    if search_query:
        lowered = search_query.lower()
        scheduled_items = [
            instance
            for instance in scheduled_items
            if lowered in instance.display_label.lower()
            or (
                (parent_trip := trip_for_instance(snapshot, instance.trip_instance_id)) is not None
                and lowered in parent_trip.label.lower()
            )
            or (
                any(lowered in trip_group.label.lower() for trip_group in groups_for_instance(snapshot, instance.trip_instance_id))
            )
        ]

    total_active_scheduled = len(scheduled_instances(snapshot, today=today))
    total_booked_scheduled = len(
        [
            instance
            for instance in snapshot.trip_instances
            if instance.anchor_date >= today
            and not instance.deleted
            and active_booking_count_for_instance(snapshot, instance.trip_instance_id) > 0
        ]
    )
    group_filter_options = [{"value": group.trip_group_id, "label": group.label} for group in group_items]

    return {
        "group_items": group_items,
        "scheduled_items": scheduled_items,
        "selected_trip_group_ids": selected_trip_group_ids,
        "search_query": search_query,
        "total_active_scheduled": total_active_scheduled,
        "total_booked_scheduled": total_booked_scheduled,
        "group_filter_options": group_filter_options,
        "today": today,
    }


def _trip_detail_view(snapshot, trip_id: str, *, today: date | None = None) -> dict[str, object]:
    today = today or date.today()
    trip = trip_by_id(snapshot, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.trip_kind == "one_time" and not trip.active:
        raise HTTPException(status_code=404, detail="Trip not found")
    route_options = route_options_for_trip(snapshot, trip.trip_id)
    future_instances = (
        horizon_instances_for_rule(snapshot, trip.trip_id, today=today)
        if trip.trip_kind == "weekly"
        else horizon_instances_for_trip(snapshot, trip.trip_id, today=today)
    )
    booked_count = sum(
        1
        for instance in future_instances
        if active_booking_count_for_instance(snapshot, instance.trip_instance_id) > 0
    )
    planned_count = len(future_instances) - booked_count
    next_open_instance = next(iter(future_instances), None)
    return {
        "trip": trip,
        "route_options": route_options,
        "route_option_views": _route_option_views(trip, route_options),
        "future_instances": future_instances,
        "planned_count": planned_count,
        "booked_count": booked_count,
        "next_open_instance": next_open_instance,
        "today": today,
    }


def _render_trip_form(
    request: Request,
    *,
    snapshot,
    trip,
    route_options,
    trip_form_state,
    route_option_state,
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
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    scheduled_view = _scheduled_view_state(snapshot, request)
    group_rule_map = {
        group.trip_group_id: recurring_rules_for_group(snapshot, group.trip_group_id)
        for group in scheduled_view["group_items"]
    }
    group_scheduled_map = {
        group.trip_group_id: scheduled_instances(
            snapshot,
            trip_group_ids={group.trip_group_id},
            today=scheduled_view["today"],
        )
        for group in scheduled_view["group_items"]
    }
    context = base_context(
        request,
        page="trips",
        snapshot=snapshot,
        horizon_instances_for_trip=horizon_instances_for_trip,
        horizon_instances_for_rule=horizon_instances_for_rule,
        instances_for_trip=instances_for_trip,
        trip_groups=trip_groups,
        recurring_rules_for_group=recurring_rules_for_group,
        route_options_for_trip=route_options_for_trip,
        booking_for_instance=booking_for_instance,
        best_tracker=best_tracker,
        trackers_for_instance=trackers_for_instance,
        trip_for_instance=trip_for_instance,
        group_for_trip=group_for_trip,
        groups_for_trip=groups_for_trip,
        group_for_instance=group_for_instance,
        groups_for_instance=groups_for_instance,
        recurring_rule_for_instance=recurring_rule_for_instance,
        groups_for_rule=groups_for_rule,
        trip_focus_url=trip_focus_url,
        group_rule_map=group_rule_map,
        group_scheduled_map=group_scheduled_map,
        **scheduled_view,
    )
    partial = request.query_params.get("partial")
    if partial == "scheduled":
        template_name = "partials/scheduled_trips_section.html"
    elif partial == "scheduled-results":
        template_name = "partials/scheduled_trips_results.html"
    else:
        template_name = "trips.html"
    return get_templates(request).TemplateResponse(
        request=request,
        name=template_name,
        context=context,
    )


@router.get("/trips/new", response_class=HTMLResponse)
def new_trip(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    trip_kind = str(request.query_params.get("trip_kind", "weekly")).strip() or "weekly"
    trip_group_id = str(request.query_params.get("trip_group_id", "")).strip()
    return _render_trip_form(
        request,
        snapshot=snapshot,
        trip=None,
        route_options=[],
        trip_form_state={
            **_trip_form_state(None, []),
            "trip_kind": trip_kind if trip_kind in {"one_time", "weekly"} else "weekly",
            "trip_group_ids": [trip_group_id] if trip_group_id else [],
        },
        route_option_state=_route_option_state([]),
    )


@router.get("/trips/{trip_id}", response_class=HTMLResponse)
def trip_detail(
    trip_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> Response:
    snapshot = load_snapshot(repository)
    detail_view = _trip_detail_view(snapshot, trip_id)
    trip = detail_view["trip"]
    if trip.trip_kind == "one_time":
        one_time_instances = instances_for_trip(snapshot, trip.trip_id)
        if one_time_instances:
            return RedirectResponse(
                url=f"/trip-instances/{one_time_instances[0].trip_instance_id}",
                status_code=303,
            )
    return get_templates(request).TemplateResponse(
        request=request,
        name="trip_detail.html",
        context=base_context(
            request,
            page="trips",
            snapshot=snapshot,
            best_tracker=best_tracker,
            booking_for_instance=booking_for_instance,
            trackers_for_instance=trackers_for_instance,
            trip_focus_url=trip_focus_url,
            **detail_view,
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
    if trip.trip_kind == "one_time" and not trip.active:
        raise HTTPException(status_code=404, detail="Trip not found")
    route_options = route_options_for_trip(snapshot, trip.trip_id)
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
    trip_group_ids_json = str(form.get("trip_group_ids_json", "[]") or "[]")
    preference_mode = str(form.get("preference_mode", "equal")).strip() or "equal"
    anchor_date_value = str(form.get("anchor_date", "")).strip()
    anchor_weekday = str(form.get("anchor_weekday", "")).strip()
    route_options_json = str(form.get("route_options_json", "[]"))
    try:
        parsed_trip_group_ids = json.loads(trip_group_ids_json or "[]")
    except ValueError:
        parsed_trip_group_ids = []
    trip_group_ids = [
        str(item).strip()
        for item in parsed_trip_group_ids
        if str(item).strip()
    ]
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
            snapshot = load_snapshot(repository)
        queued_count = queue_refresh_for_trip(
            snapshot,
            repository,
            trip_id=trip.trip_id,
            include_test_data=include_test_data_for_processing(snapshot.app_state),
        )
        message = queued_refresh_message("Trip saved", queued_count)
        warning_count = _linked_booking_route_warning_count(snapshot, trip)
        if warning_count:
            booking_noun = "booking" if warning_count == 1 else "bookings"
            verb = "does" if warning_count == 1 else "do"
            message = (
                f"{message} {warning_count} linked {booking_noun} "
                f"{verb} not match a unique tracked route."
            )
        return redirect_with_message(f"/trips/{trip.trip_id}", message)
    except ValueError as exc:
        snapshot = load_snapshot(repository)
        return _render_trip_form(
            request,
            snapshot=snapshot,
            trip=existing_trip,
            route_options=[],
            error_message=str(exc),
            trip_form_state={
                "trip_id": trip_id or "",
                "label": label,
                "trip_kind": trip_kind,
                "trip_group_ids": trip_group_ids,
                "preference_mode": preference_mode,
                "anchor_date": anchor_date_value,
                "anchor_weekday": anchor_weekday or "Monday",
            },
            route_option_state=_route_option_state_from_payloads(raw_route_option_state),
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
    return redirect_back(request, fallback_url="/trips", message="Trip paused")


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
        fallback_url="/trips",
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
    active_booking = next(
        (
            item
            for item in repository.load_bookings()
            if item.trip_instance_id in {
                instance.trip_instance_id
                for instance in repository.load_trip_instances()
                if instance.trip_id == trip.trip_id
            }
            and item.status == "active"
        ),
        None,
    )
    if active_booking is not None:
        return redirect_back(
            request,
            fallback_url=f"/trips/{trip_id}",
            message="Unlink or cancel the booking before deleting this trip.",
            message_kind="error",
        )
    delete_trip(repository, trip_id)
    sync_and_persist(repository)
    return redirect_with_message("/trips", "Trip deleted")


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
            fallback_url=f"/trip-instances/{trip_instance_id}",
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
        f"/trip-instances/{trip_instance.trip_instance_id}",
        queued_refresh_message("Trip detached", queued_count),
    )


@router.post("/trip-instances/{trip_instance_id}/delete-generated")
def delete_generated_trip_instance_action(
    trip_instance_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    snapshot = load_snapshot(repository, recompute=False)
    existing_instance = next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)
    if existing_instance is None:
        raise HTTPException(status_code=404, detail="Trip instance not found")
    redirect_url = "/trips"
    if existing_instance.recurring_rule_trip_id:
        recurring_rule = trip_by_id(snapshot, existing_instance.recurring_rule_trip_id)
        recurring_rule_groups = groups_for_rule(snapshot, recurring_rule) if recurring_rule else []
        if len(recurring_rule_groups) == 1:
            redirect_url = f"/groups/{recurring_rule_groups[0].trip_group_id}"
    try:
        delete_generated_trip_instance(repository, trip_instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        return redirect_back(
            request,
            fallback_url=f"/trip-instances/{trip_instance_id}",
            message=str(exc),
            message_kind="error",
        )
    sync_and_persist(repository)
    return redirect_with_message(redirect_url, "Trip deleted")
