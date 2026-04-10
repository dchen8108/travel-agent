from __future__ import annotations

from datetime import date

from app.services.dashboard_queries import scheduled_instances
from app.services.scheduled_trip_display import trip_ui_label
from app.services.scheduled_trip_state import active_booking_count_for_instance, rebook_savings


def group_trip_pill_view(snapshot, instance) -> dict[str, object]:
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
    title = trip_ui_label(snapshot, instance.trip_instance_id)
    return {
        "instance": instance,
        "href": f"/trip-instances/{instance.trip_instance_id}",
        "label": instance.anchor_date.strftime("%b %d"),
        "title": f"{title} · {status_label} · {instance.anchor_date.strftime('%a, %b %d')}",
        "tone": tone,
    }


def group_summary_view(snapshot, group, *, today: date) -> dict[str, object]:
    upcoming = scheduled_instances(snapshot, trip_group_ids={group.trip_group_id}, today=today)
    return {
        "group": group,
        "upcoming_trip_views": [group_trip_pill_view(snapshot, instance) for instance in upcoming],
    }
