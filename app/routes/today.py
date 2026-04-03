from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.money import format_money
from app.services.dashboard import (
    active_booking_count_for_instance,
    best_tracker,
    booking_for_instance,
    groups_for_instance,
    recurring_rules_for_group,
    scheduled_instances,
    load_snapshot,
    rebook_savings,
    recurring_rule_for_instance,
    scheduled_ledger_view,
    trip_groups,
    trip_for_instance,
    trip_focus_url,
    trip_lifecycle_status_label,
    trip_lifecycle_status_tone,
    trip_monitoring_status_label,
    trip_recommended_action,
    unmatched_booking_resolution_views,
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
        else:
            detail = "Still gathering current prices"

    if booking is not None and savings is not None:
        phase_label = "Rebook"
        phase_tone = "accent"
    elif booking is not None:
        phase_label = "Booked"
        phase_tone = "success"
    else:
        phase_label = "To book"
        phase_tone = "warning"

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
        "phase_label": phase_label,
        "phase_tone": phase_tone,
        "href": f"/trip-instances/{instance.trip_instance_id}",
    }


def _group_dashboard_view(snapshot, group, *, today: date) -> dict[str, object]:
    upcoming = scheduled_instances(snapshot, trip_group_ids={group.trip_group_id}, today=today)
    rule_count = len(recurring_rules_for_group(snapshot, group.trip_group_id))
    booked_count = sum(
        1
        for instance in upcoming
        if active_booking_count_for_instance(snapshot, instance.trip_instance_id) > 0
    )
    upcoming_trip_views = []
    for instance in upcoming[:8]:
        trip = trip_for_instance(snapshot, instance.trip_instance_id)
        active_booking_count = active_booking_count_for_instance(snapshot, instance.trip_instance_id)
        savings = rebook_savings(snapshot, instance.trip_instance_id)
        if active_booking_count > 0 and savings is not None:
            tone = "accent"
            status_label = "Rebook"
        elif active_booking_count > 0:
            tone = "success"
            status_label = "Booked"
        else:
            tone = "warning"
            status_label = "Planned"
        title = trip.label if trip is not None else instance.display_label
        upcoming_trip_views.append(
            {
                "instance": instance,
                "href": f"/trip-instances/{instance.trip_instance_id}",
                "label": instance.anchor_date.strftime("%b %d"),
                "title": f"{title} · {status_label} · {instance.anchor_date.strftime('%a, %b %d')}",
                "tone": tone,
            }
        )
    if group.description:
        summary = group.description
    elif upcoming:
        summary = (
            f"Next on {upcoming[0].anchor_date.strftime('%a, %b %d')} · "
            f"{len(upcoming)} upcoming trip{'s' if len(upcoming) != 1 else ''} across "
            f"{rule_count} recurring "
            f"plan{'s' if rule_count != 1 else ''}."
        )
    else:
        summary = (
            f"{rule_count} recurring "
            f"plan{'s' if rule_count != 1 else ''} ready for future travel."
            if rule_count
            else "Ready for one-off trips or recurring plans when you need them."
        )
    return {
        "group": group,
        "upcoming_count": len(upcoming),
        "next_instance": upcoming[0] if upcoming else None,
        "booked_count": booked_count,
        "planned_count": max(0, len(upcoming) - booked_count),
        "rule_count": rule_count,
        "summary": summary,
        "upcoming_trip_views": upcoming_trip_views,
    }


@router.get("/", response_class=HTMLResponse)
def today(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    today = date.today()
    scheduled_view = scheduled_ledger_view(
        snapshot,
        today=today,
        selected_trip_group_ids=request.query_params.getlist("trip_group_id"),
        search_query=str(request.query_params.get("q", "")),
    )
    partial = request.query_params.get("partial")
    if partial in {"scheduled", "scheduled-results"}:
        template_name = (
            "partials/scheduled_trips_section.html"
            if partial == "scheduled"
            else "partials/scheduled_trips_results.html"
        )
        return get_templates(request).TemplateResponse(
            request=request,
            name=template_name,
            context=base_context(
                request,
                page="dashboard",
                snapshot=snapshot,
                trip_focus_url=trip_focus_url,
                scheduled_filter_action_path="/",
                scheduled_filter_clear_path="/#all-travel",
                **scheduled_view,
            ),
        )
    unmatched_views = unmatched_booking_resolution_views(snapshot)
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
    next_trip = upcoming_instances[0] if upcoming_instances else None

    rebook_views = [_instance_dashboard_view(snapshot, instance) for instance in rebook_instances[:6]]
    action_window_cutoff = today + timedelta(days=10)
    book_now_views = [
        _instance_dashboard_view(snapshot, instance)
        for instance in planned_instances
        if instance.anchor_date <= action_window_cutoff
    ][:4]
    action_count = len(unmatched_views) + len(rebook_views) + len(book_now_views)

    monitoring_labels = [
        trip_monitoring_status_label(snapshot, instance.trip_instance_id)
        for instance in upcoming_instances
    ]
    tracking_count = sum(1 for label in monitoring_labels if label == "Tracking")
    initializing_count = sum(1 for label in monitoring_labels if label == "Initializing")
    no_match_count = sum(1 for label in monitoring_labels if label == "No matches")

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
        )
    ]
    return get_templates(request).TemplateResponse(
        request=request,
        name="today.html",
        context=base_context(
            request,
            page="dashboard",
            snapshot=snapshot,
            unmatched_views=unmatched_views,
            planned_instances=planned_instances,
            rebook_views=rebook_views,
            book_now_views=book_now_views,
            group_views=group_views,
            scheduled_filter_action_path="/",
            scheduled_filter_clear_path="/#all-travel",
            action_count=action_count,
            next_trip=next_trip,
            total_upcoming=len(upcoming_instances),
            total_booked_monitoring=len(booked_instances),
            tracking_count=tracking_count,
            initializing_count=initializing_count,
            no_match_count=no_match_count,
            booking_for_instance=booking_for_instance,
            best_tracker=best_tracker,
            trip_for_instance=trip_for_instance,
            trip_focus_url=trip_focus_url,
            **scheduled_view,
        ),
    )
