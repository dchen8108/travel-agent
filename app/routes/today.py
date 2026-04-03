from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.money import format_money
from app.services.dashboard import (
    active_booking_count_for_instance,
    best_tracker,
    booking_for_instance,
    booking_route_tracking_state,
    groups_for_instance,
    groups_for_rule,
    recurring_trips,
    route_options_for_trip,
    scheduled_instances,
    load_snapshot,
    rebook_savings,
    recurring_rule_for_instance,
    trip_groups,
    trip_for_instance,
    trip_lifecycle_status_label,
    trip_lifecycle_status_tone,
    trip_monitoring_status_label,
    trip_recommended_action,
    trip_focus_url,
)
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(tags=["today"])


def _best_route_signal(tracker) -> str:
    if tracker is None:
        return ""
    if tracker.latest_winning_origin_airport and tracker.latest_winning_destination_airport:
        return f"{tracker.latest_winning_origin_airport} → {tracker.latest_winning_destination_airport}"
    if tracker.latest_match_summary:
        return tracker.latest_match_summary
    return ""


def _instance_dashboard_view(snapshot, instance) -> dict[str, object]:
    trip = trip_for_instance(snapshot, instance.trip_instance_id)
    recurring_rule = recurring_rule_for_instance(snapshot, instance.trip_instance_id)
    tracker = best_tracker(snapshot, instance.trip_instance_id)
    booking = booking_for_instance(snapshot, instance.trip_instance_id)
    active_booking_count = active_booking_count_for_instance(snapshot, instance.trip_instance_id)
    savings = rebook_savings(snapshot, instance.trip_instance_id)
    lifecycle_label = trip_lifecycle_status_label(snapshot, instance.trip_instance_id)
    monitoring_label = trip_monitoring_status_label(snapshot, instance.trip_instance_id)
    recommended_action = trip_recommended_action(snapshot, instance.trip_instance_id)
    group_labels = [group.label for group in groups_for_instance(snapshot, instance.trip_instance_id)]
    title = trip.label if trip else instance.display_label
    if group_labels:
        context_label = " · ".join(group_labels)
    elif recurring_rule is not None and (trip is None or recurring_rule.trip_id != trip.trip_id):
        context_label = recurring_rule.label
    elif instance.display_label != title:
        context_label = instance.display_label
    else:
        context_label = ""

    best_signal = _best_route_signal(tracker)
    if booking is not None:
        if active_booking_count > 1:
            if tracker is not None and tracker.latest_observed_price is not None:
                detail = (
                    f"{active_booking_count} active bookings · "
                    f"best alternative {format_money(tracker.latest_observed_price)}"
                )
            else:
                detail = f"{active_booking_count} active bookings"
        elif savings is not None and tracker is not None and tracker.latest_observed_price is not None:
            detail = (
                f"Booked {format_money(booking.booked_price)} · "
                f"best alternative {format_money(tracker.latest_observed_price)} · "
                f"save {format_money(savings)}"
            )
        elif tracker is not None and tracker.latest_observed_price is not None:
            detail = (
                f"Booked {format_money(booking.booked_price)} · "
                f"tracking {format_money(tracker.latest_observed_price)}"
            )
        else:
            detail = f"Booked {format_money(booking.booked_price)}"
    else:
        if tracker is not None and tracker.latest_observed_price is not None and best_signal:
            detail = f"Best alternative {best_signal} · {format_money(tracker.latest_observed_price)}"
        elif tracker is not None and tracker.latest_observed_price is not None:
            detail = f"Best alternative {format_money(tracker.latest_observed_price)}"
        elif monitoring_label == "No matches":
            detail = "No matching flights right now"
        elif monitoring_label == "No searches":
            detail = "No tracked routes yet"
        else:
            detail = "Still gathering current prices"

    return {
        "instance": instance,
        "trip": trip,
        "title": title,
        "context_label": context_label,
        "tracker": tracker,
        "booking": booking,
        "active_booking_count": active_booking_count,
        "lifecycle_label": lifecycle_label,
        "lifecycle_tone": trip_lifecycle_status_tone(snapshot, instance.trip_instance_id),
        "monitoring_label": monitoring_label,
        "recommended_action": recommended_action,
        "detail": detail,
        "savings": savings,
        "href": f"/trip-instances/{instance.trip_instance_id}",
    }


def _recent_booking_view(snapshot, booking) -> dict[str, object]:
    trip = trip_for_instance(snapshot, booking.trip_instance_id)
    route_tracking = booking_route_tracking_state(snapshot, booking)
    return {
        "booking": booking,
        "trip": trip,
        "route_tracking": route_tracking,
        "href": (
            f"/trip-instances/{booking.trip_instance_id}"
            if booking.trip_instance_id
            else "/bookings"
        ),
    }


def _rule_dashboard_view(snapshot, rule, *, today: date) -> dict[str, object]:
    future_instances = [
        instance
        for instance in scheduled_instances(snapshot, today=today)
        if instance.recurring_rule_trip_id == rule.trip_id
    ]
    next_instance = future_instances[0] if future_instances else None
    return {
        "rule": rule,
        "groups": groups_for_rule(snapshot, rule),
        "route_count": len(route_options_for_trip(snapshot, rule.trip_id)),
        "upcoming_count": len(future_instances),
        "next_instance": next_instance,
        "booked_count": sum(
            1
            for instance in future_instances
            if active_booking_count_for_instance(snapshot, instance.trip_instance_id) > 0
        ),
    }


def _group_dashboard_view(snapshot, group, *, today: date) -> dict[str, object]:
    upcoming = scheduled_instances(snapshot, trip_group_ids={group.trip_group_id}, today=today)
    return {
        "group": group,
        "upcoming_count": len(upcoming),
        "next_instance": upcoming[0] if upcoming else None,
        "booked_count": sum(
            1
            for instance in upcoming
            if active_booking_count_for_instance(snapshot, instance.trip_instance_id) > 0
        ),
        "rule_count": len(
            [
                rule
                for rule in recurring_trips(snapshot)
                if any(target_group.trip_group_id == group.trip_group_id for target_group in groups_for_rule(snapshot, rule))
            ]
        ),
    }


@router.get("/", response_class=HTMLResponse)
def today(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    today = date.today()
    open_unmatched = [item for item in snapshot.unmatched_bookings if item.resolution_status == "open"]
    upcoming_instances = scheduled_instances(snapshot, today=today)
    planned_instances = [
        instance for instance in upcoming_instances if active_booking_count_for_instance(snapshot, instance.trip_instance_id) == 0
    ]
    booked_instances = [
        instance for instance in upcoming_instances if active_booking_count_for_instance(snapshot, instance.trip_instance_id) > 0
    ]
    rebook_instances = [
        instance for instance in booked_instances if rebook_savings(snapshot, instance.trip_instance_id) is not None
    ]
    action_count = len(open_unmatched) + len(rebook_instances)
    open_savings_total = sum(rebook_savings(snapshot, instance.trip_instance_id) or 0 for instance in rebook_instances)
    next_trip = upcoming_instances[0] if upcoming_instances else None

    planned_views = [_instance_dashboard_view(snapshot, instance) for instance in planned_instances[:10]]
    booked_views = [_instance_dashboard_view(snapshot, instance) for instance in booked_instances[:10]]
    rebook_views = [_instance_dashboard_view(snapshot, instance) for instance in rebook_instances[:6]]

    recent_booking_views = [
        _recent_booking_view(snapshot, booking)
        for booking in sorted(snapshot.bookings, key=lambda item: item.booked_at, reverse=True)[:4]
    ]

    recurring_rule_views = [
        _rule_dashboard_view(snapshot, rule, today=today)
        for rule in sorted(
            recurring_trips(snapshot),
            key=lambda item: (
                not item.active,
                next(
                    (
                        instance.anchor_date
                        for instance in scheduled_instances(snapshot, today=today)
                        if instance.recurring_rule_trip_id == item.trip_id
                    ),
                    date.max,
                ),
                item.label.lower(),
            ),
        )[:6]
    ]
    group_views = [
        _group_dashboard_view(snapshot, group, today=today)
        for group in sorted(
            trip_groups(snapshot),
            key=lambda item: (
                next(
                    (
                        instance.anchor_date
                        for instance in scheduled_instances(snapshot, trip_group_ids={item.trip_group_id}, today=today)
                    ),
                    date.max,
                ),
                item.label.lower(),
            ),
        )[:5]
    ]

    return get_templates(request).TemplateResponse(
        request=request,
        name="today.html",
        context=base_context(
            request,
            page="dashboard",
            snapshot=snapshot,
            open_unmatched=open_unmatched,
            planned_instances=planned_instances,
            booked_instances=booked_instances,
            planned_views=planned_views,
            booked_views=booked_views,
            rebook_views=rebook_views,
            recent_booking_views=recent_booking_views,
            recurring_rule_views=recurring_rule_views,
            group_views=group_views,
            action_count=action_count,
            next_trip=next_trip,
            total_upcoming=len(upcoming_instances),
            total_booked_monitoring=len(booked_instances),
            total_groups=len(snapshot.trip_groups),
            total_rules=len([trip for trip in snapshot.trips if trip.trip_kind == "weekly"]),
            open_savings_total=open_savings_total,
            booking_for_instance=booking_for_instance,
            best_tracker=best_tracker,
            trip_for_instance=trip_for_instance,
            trip_focus_url=trip_focus_url,
        ),
    )
