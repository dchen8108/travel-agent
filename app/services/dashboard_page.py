from __future__ import annotations

from datetime import date, timedelta

from app.money import format_money
from app.services.collection_display import group_summary_view
from app.services.dashboard_booking_views import unmatched_booking_resolution_views
from app.services.dashboard_navigation import trip_focus_url
from app.services.dashboard_queries import scheduled_instances, scheduled_ledger_view, trip_groups
from app.services.scheduled_trip_display import trip_ui_context_label, trip_ui_label
from app.services.scheduled_trip_state import (
    active_booking_count_for_instance,
    best_tracker,
    booking_for_instance,
    rebook_savings,
    trip_lifecycle_status_label,
    trip_lifecycle_status_tone,
    trip_monitoring_status_label,
    trip_recommended_action,
)
from app.services.snapshot_queries import trip_for_instance


def _best_route_signal(tracker) -> str:
    if tracker is None:
        return ""
    if tracker.latest_winning_origin_airport and tracker.latest_winning_destination_airport:
        return f"{tracker.latest_winning_origin_airport} → {tracker.latest_winning_destination_airport}"
    if tracker.latest_match_summary:
        return tracker.latest_match_summary
    return ""


def instance_dashboard_view(snapshot, instance) -> dict[str, object]:
    trip = trip_for_instance(snapshot, instance.trip_instance_id)
    tracker = best_tracker(snapshot, instance.trip_instance_id)
    booking = booking_for_instance(snapshot, instance.trip_instance_id)
    active_booking_count = active_booking_count_for_instance(snapshot, instance.trip_instance_id)
    savings = rebook_savings(snapshot, instance.trip_instance_id)
    lifecycle_label = trip_lifecycle_status_label(snapshot, instance.trip_instance_id)
    monitoring_label = trip_monitoring_status_label(snapshot, instance.trip_instance_id)
    recommended_action = trip_recommended_action(snapshot, instance.trip_instance_id)
    title = trip_ui_label(snapshot, instance.trip_instance_id)
    context_label = trip_ui_context_label(snapshot, instance.trip_instance_id)

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
        "href": trip_focus_url(snapshot, trip.trip_id, trip_instance_id=instance.trip_instance_id),
    }


def build_dashboard_page_context(
    snapshot,
    *,
    today: date,
    selected_trip_group_ids: list[str] | None = None,
    include_booked: bool = True,
    collection_editor_state: dict[str, object] | None = None,
) -> dict[str, object]:
    scheduled_view = scheduled_ledger_view(
        snapshot,
        today=today,
        selected_trip_group_ids=selected_trip_group_ids,
        include_booked=include_booked,
    )
    unmatched_views = unmatched_booking_resolution_views(snapshot)
    upcoming_instances = scheduled_instances(snapshot, today=today)
    planned_instances = [
        instance for instance in upcoming_instances if active_booking_count_for_instance(snapshot, instance.trip_instance_id) == 0
    ]
    booked_instances = [
        instance for instance in upcoming_instances if active_booking_count_for_instance(snapshot, instance.trip_instance_id) > 0
    ]
    overbooked_window_cutoff = today + timedelta(days=snapshot.app_state.dashboard_overbooked_window_days)
    overbooked_instances = [
        instance
        for instance in booked_instances
        if active_booking_count_for_instance(snapshot, instance.trip_instance_id) > 1
        and instance.anchor_date <= overbooked_window_cutoff
    ]
    overbooked_instance_ids = {
        instance.trip_instance_id for instance in overbooked_instances
    }
    rebook_instances = [
        instance
        for instance in booked_instances
        if instance.trip_instance_id not in overbooked_instance_ids
        and rebook_savings(snapshot, instance.trip_instance_id) is not None
    ]
    overbooked_views = [instance_dashboard_view(snapshot, instance) for instance in overbooked_instances]
    rebook_views = [instance_dashboard_view(snapshot, instance) for instance in rebook_instances]
    action_window_cutoff = today + timedelta(weeks=snapshot.app_state.dashboard_needs_booking_window_weeks)
    book_now_views = [
        instance_dashboard_view(snapshot, instance)
        for instance in planned_instances
        if instance.anchor_date <= action_window_cutoff
    ]
    group_views = [
        group_summary_view(snapshot, group, today=today)
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
    return {
        "unmatched_views": unmatched_views,
        "planned_instances": planned_instances,
        "overbooked_views": overbooked_views,
        "rebook_views": rebook_views,
        "book_now_views": book_now_views,
        "group_views": group_views,
        "total_upcoming": len(upcoming_instances),
        "collection_editor_state": collection_editor_state,
        "scheduled_filter_action_path": "/",
        "scheduled_filter_clear_path": "/#all-travel",
        **scheduled_view,
    }
