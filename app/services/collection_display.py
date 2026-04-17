from __future__ import annotations

from datetime import date

from app.services.dashboard_navigation import trip_focus_url
from app.services.dashboard_queries import recurring_rules_for_group, scheduled_instances
from app.services.scheduled_trip_display import trip_ui_label
from app.services.scheduled_trip_state import active_booking_count_for_instance
from app.services.trip_attention import dashboard_trip_attention_kind, trip_attention_title


def group_trip_pill_view(snapshot, instance, *, today: date) -> dict[str, object]:
    active_booking_count = active_booking_count_for_instance(snapshot, instance.trip_instance_id)
    lifecycle = "booked" if active_booking_count > 0 else "planned"
    status_label = "Booked" if lifecycle == "booked" else "Planned"
    attention_kind = dashboard_trip_attention_kind(snapshot, instance, today=today)
    attention_label = trip_attention_title(attention_kind)
    title = trip_ui_label(snapshot, instance.trip_instance_id)
    return {
        "instance": instance,
        "href": trip_focus_url(snapshot, instance.trip_id, trip_instance_id=instance.trip_instance_id),
        "label": instance.anchor_date.strftime("%b %d"),
        "title": (
            f"{title} · {attention_label or status_label} · {instance.anchor_date.strftime('%a, %b %d')}"
        ),
        "lifecycle": lifecycle,
        "attention_kind": attention_kind or "",
    }


def group_recurring_rule_view(rule) -> dict[str, object]:
    return {
        "trip_id": rule.trip_id,
        "label": rule.label,
        "anchor_weekday": rule.anchor_weekday,
        "active": rule.active,
        "edit_href": f"/trips/{rule.trip_id}/edit",
        "toggle_action": f"/trips/{rule.trip_id}/{'pause' if rule.active else 'activate'}",
        "toggle_label": "Active" if rule.active else "Paused",
    }


def group_summary_view(snapshot, group, *, today: date) -> dict[str, object]:
    upcoming = scheduled_instances(snapshot, trip_group_ids={group.trip_group_id}, today=today)
    recurring_rules = recurring_rules_for_group(snapshot, group.trip_group_id)
    return {
        "group": group,
        "recurring_rule_views": [group_recurring_rule_view(rule) for rule in recurring_rules],
        "upcoming_trip_views": [group_trip_pill_view(snapshot, instance, today=today) for instance in upcoming],
    }
