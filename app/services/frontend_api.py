from __future__ import annotations

import json
from datetime import date

from fastapi import HTTPException

from app.catalog import catalogs_json
from app.money import format_money
from app.models.base import TripInstanceInheritanceMode, TripKind
from app.models.booking import Booking
from app.services.collection_display import group_summary_view
from app.services.dashboard_booking_views import booking_reference_label, default_trip_label_for_booking
from app.services.dashboard_page import dashboard_attention_views
from app.services.dashboard_queries import scheduled_ledger_view, trip_groups
from app.services.dashboard_trip_panels import tracker_search_rows, trip_instance_dashboard_context
from app.services.scheduled_trip_display import (
    booking_offer_summary,
    trip_row_actions_view,
    trip_row_summary,
    trip_ui_label,
    trip_ui_picker_label,
)
from app.services.scheduled_trip_state import booking_route_tracking_state, bookings_for_instance
from app.services.snapshot_queries import (
    recurring_rule_for_instance,
    trip_for_instance,
    trip_group_by_id,
    trip_instance_by_id,
)
from app.services.trip_editor import edit_trip_form_payload, new_trip_form_payload


def _date_tile_value(value: date) -> dict[str, str]:
    return {
        "weekday": value.strftime("%a").upper(),
        "monthDay": value.strftime("%b %d"),
    }


def _offer_value(offer: dict[str, object] | None) -> dict[str, object] | None:
    if offer is None:
        return None
    return {
        "label": str(offer.get("label", "")),
        "detail": str(offer.get("detail", "")),
        "metaLabel": str(offer.get("meta_label", "")),
        "dayDeltaLabel": str(offer.get("day_delta_label", "")),
        "priceLabel": str(offer.get("price_label", "")),
        "href": str(offer.get("href", "")),
        "tone": str(offer.get("tone", "neutral")),
        "priceIsStatus": bool(offer.get("price_is_status", False)),
        "statusKind": str(offer.get("status_kind", "")),
    }


def _delete_capability(snapshot, trip_instance_id: str) -> dict[str, object] | None:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    trip = trip_for_instance(snapshot, trip_instance_id)
    recurring_rule = recurring_rule_for_instance(snapshot, trip_instance_id)
    if instance is None or trip is None:
        return None
    if (
        trip.trip_kind == TripKind.WEEKLY
        and instance.inheritance_mode == TripInstanceInheritanceMode.ATTACHED
        and recurring_rule is not None
    ):
        return {
            "kind": "generated",
            "confirmation": {
                "title": "Delete this generated trip?",
                "description": "This date will be removed from the recurring trip and will stop background fare checks unless you recreate it later.",
                "action": "Delete trip",
                "cancel": "Keep trip",
            },
        }
    if trip.trip_kind == TripKind.ONE_TIME and trip.active:
        return {
            "kind": "trip",
            "confirmation": {
                "title": "Delete this one-time trip?",
                "description": "It will disappear from the active trip workflow and stop background fare checks for this date.",
                "action": "Delete trip",
                "cancel": "Keep trip",
            },
        }
    return None


def trip_identity_value(snapshot, trip_instance_id: str) -> dict[str, object]:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="Scheduled trip not found")
    actions = trip_row_actions_view(snapshot, trip_instance_id)
    return {
        "tripInstanceId": instance.trip_instance_id,
        "tripId": instance.trip_id,
        "title": trip_ui_label(snapshot, trip_instance_id),
        "anchorDate": instance.anchor_date.isoformat(),
        "dateTile": _date_tile_value(instance.anchor_date),
        "editHref": str(actions.get("edit_href", "")),
        "delete": _delete_capability(snapshot, trip_instance_id),
    }


def trip_row_value(snapshot, trip_instance_id: str) -> dict[str, object]:
    instance = trip_instance_by_id(snapshot, trip_instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="Scheduled trip not found")
    row = trip_row_summary(snapshot, trip_instance_id)
    actions = trip_row_actions_view(snapshot, trip_instance_id)
    return {
        "trip": trip_identity_value(snapshot, trip_instance_id),
        "bookedOffer": _offer_value(row.get("booked_offer")),
        "currentOffer": _offer_value(row.get("current_offer")),
        "actions": {
            "showBookingModal": bool(actions.get("show_booking_modal")),
            "canCreateBooking": bool(actions.get("can_create_booking")),
            "showTrackers": bool(actions.get("show_trackers")),
        },
    }


def collection_card_value(snapshot, trip_group_id: str, *, today: date) -> dict[str, object]:
    group = trip_group_by_id(snapshot, trip_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    view = group_summary_view(snapshot, group, today=today)
    return {
        "groupId": group.trip_group_id,
        "label": group.label,
        "createTripHref": f"/trips/new?trip_group_id={group.trip_group_id}",
        "recurringTrips": [
            {
                "tripId": item["trip_id"],
                "label": item["label"],
                "anchorWeekday": item["anchor_weekday"],
                "active": bool(item["active"]),
                "editHref": item["edit_href"],
            }
            for item in view["recurring_rule_views"]
        ],
        "upcomingTrips": [
            {
                "href": item["href"],
                "label": item["label"],
                "title": item["title"],
                "tone": item["tone"],
            }
            for item in view["upcoming_trip_views"]
        ],
    }


def _trip_picker_option_group_value(snapshot, trip_instances: list[object], *, label: str) -> dict[str, object]:
    return {
        "label": label,
        "options": [
            {
                "value": instance.trip_instance_id,
                "label": trip_ui_picker_label(snapshot, instance.trip_instance_id),
            }
            for instance in trip_instances
        ],
    }


def _action_items_value(snapshot, *, today: date) -> list[dict[str, object]]:
    attention = dashboard_attention_views(snapshot, today=today)
    items: list[dict[str, object]] = []

    for card in attention["unmatched_views"]:
        unmatched = card["unmatched"]
        option_groups = []
        if card["suggested_trip_instances"]:
            option_groups.append(
                _trip_picker_option_group_value(
                    snapshot,
                    card["suggested_trip_instances"],
                    label="Suggested matches",
                )
            )
        if card["upcoming_trip_instances"]:
            option_groups.append(
                _trip_picker_option_group_value(
                    snapshot,
                    card["upcoming_trip_instances"],
                    label="Upcoming trips",
                )
            )
        if card["past_trip_instances"]:
            option_groups.append(
                _trip_picker_option_group_value(
                    snapshot,
                    card["past_trip_instances"],
                    label="Past trips",
                )
            )
        items.append(
            {
                "kind": "unmatchedBooking",
                "title": "Link booking",
                "sourceLabel": f"{booking_reference_label(unmatched)} · {unmatched.source.replace('_', ' ')}",
                "suggestedTripLabel": default_trip_label_for_booking(unmatched),
                "unmatchedBookingId": unmatched.unmatched_booking_id,
                "offer": _offer_value(
                    booking_offer_summary(
                        unmatched,
                        anchor_date=unmatched.departure_date,
                    )
                ),
                "tripOptions": option_groups,
                "createTripHref": f"/trips/new?unmatched_booking_id={unmatched.unmatched_booking_id}",
            }
        )

    for card in attention["overbooked_views"]:
        items.append(
            {
                "kind": "tripAttention",
                "attentionKind": "overbooked",
                "title": "Multiple bookings",
                "badge": f"{card['active_booking_count']} active",
                "row": trip_row_value(snapshot, card["instance"].trip_instance_id),
            }
        )
    for card in attention["rebook_views"]:
        items.append(
            {
                "kind": "tripAttention",
                "attentionKind": "rebook",
                "title": "Price drop",
                "badge": f"{format_money(card['savings'])} lower" if card.get("savings") else "",
                "row": trip_row_value(snapshot, card["instance"].trip_instance_id),
            }
        )
    for card in attention["book_now_views"]:
        items.append(
            {
                "kind": "tripAttention",
                "attentionKind": "needsBooking",
                "title": "Needs booking",
                "badge": card["instance"].anchor_date.strftime("%b %d"),
                "row": trip_row_value(snapshot, card["instance"].trip_instance_id),
            }
        )
    return items


def dashboard_payload(
    snapshot,
    *,
    today: date,
    selected_trip_group_ids: list[str] | None = None,
    include_booked: bool = True,
) -> dict[str, object]:
    scheduled_view = scheduled_ledger_view(
        snapshot,
        today=today,
        selected_trip_group_ids=selected_trip_group_ids,
        include_booked=include_booked,
    )
    return {
        "today": today.isoformat(),
        "filters": {
            "selectedTripGroupIds": list(scheduled_view["selected_trip_group_ids"]),
            "includeBooked": bool(scheduled_view["include_booked"]),
            "groupOptions": [
                {
                    "value": item["value"],
                    "label": item["label"],
                }
                for item in scheduled_view["group_filter_options"]
            ],
        },
        "counts": {
            "totalUpcoming": int(scheduled_view["total_active_scheduled"]),
            "totalBooked": int(scheduled_view["total_booked_scheduled"]),
        },
        "collections": [
            collection_card_value(snapshot, group.trip_group_id, today=today)
            for group in trip_groups(snapshot)
        ],
        "actionItems": _action_items_value(snapshot, today=today),
        "trips": [
            trip_row_value(snapshot, instance.trip_instance_id)
            for instance in scheduled_view["scheduled_items"]
        ],
    }


def booking_form_state_value(booking: Booking | None = None, *, trip_instance_id: str = "") -> dict[str, str]:
    if booking is None:
        return {
            "bookingId": "",
            "tripInstanceId": trip_instance_id,
            "airline": "",
            "originAirport": "",
            "destinationAirport": "",
            "departureDate": "",
            "departureTime": "",
            "arrivalTime": "",
            "bookedPrice": "",
            "recordLocator": "",
            "notes": "",
        }
    return {
        "bookingId": booking.booking_id,
        "tripInstanceId": trip_instance_id or booking.trip_instance_id,
        "airline": booking.airline,
        "originAirport": booking.origin_airport,
        "destinationAirport": booking.destination_airport,
        "departureDate": booking.departure_date.isoformat(),
        "departureTime": booking.departure_time,
        "arrivalTime": booking.arrival_time,
        "bookedPrice": str(booking.booked_price),
        "recordLocator": booking.record_locator,
        "notes": booking.notes,
    }


def booking_panel_payload(
    snapshot,
    *,
    trip_instance_id: str,
    mode: str = "list",
    booking_id: str = "",
) -> dict[str, object]:
    trip_instance_dashboard_context(snapshot, trip_instance_id)
    bookings = bookings_for_instance(snapshot, trip_instance_id)
    editing_booking = next((item for item in bookings if item.booking_id == booking_id), None) if booking_id else None
    if booking_id and editing_booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    rows = [
        {
            "bookingId": booking.booking_id,
            "offer": _offer_value(
                booking_offer_summary(
                    booking,
                    anchor_date=trip_instance_by_id(snapshot, trip_instance_id).anchor_date,
                )
            ),
            "warning": booking_route_tracking_state(snapshot, booking).get("warning", ""),
        }
        for booking in bookings
    ]
    return {
        "trip": trip_identity_value(snapshot, trip_instance_id),
        "mode": mode,
        "rows": rows,
        "form": (
            {
                "values": booking_form_state_value(editing_booking, trip_instance_id=trip_instance_id)
                if mode == "edit"
                else booking_form_state_value(None, trip_instance_id=trip_instance_id),
                "submitLabel": "Save booking" if mode == "edit" else "Create booking",
            }
            if mode in {"create", "edit"}
            else None
        ),
        "catalogs": json.loads(catalogs_json()) if mode in {"create", "edit"} else None,
    }


def booking_form_payload(
    snapshot,
    *,
    trip_instance_id: str,
    booking_id: str = "",
) -> dict[str, object]:
    trip_instance_dashboard_context(snapshot, trip_instance_id)
    bookings = bookings_for_instance(snapshot, trip_instance_id)
    editing_booking = next((item for item in bookings if item.booking_id == booking_id), None) if booking_id else None
    if booking_id and editing_booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {
        "trip": trip_identity_value(snapshot, trip_instance_id),
        "mode": "edit" if editing_booking is not None else "create",
        "form": {
            "values": booking_form_state_value(editing_booking, trip_instance_id=trip_instance_id)
            if editing_booking is not None
            else booking_form_state_value(None, trip_instance_id=trip_instance_id),
            "submitLabel": "Save booking" if editing_booking is not None else "Create booking",
        },
        "catalogs": json.loads(catalogs_json()),
    }


def tracker_panel_payload(snapshot, *, trip_instance_id: str) -> dict[str, object]:
    detail = trip_instance_dashboard_context(snapshot, trip_instance_id)
    trip_instance = detail["trip_instance"]
    return {
        "trip": trip_identity_value(snapshot, trip_instance_id),
        "rows": [
            {
                "rowId": row.row_id,
                "travelDate": row.travel_date.isoformat(),
                "offer": _offer_value(row.row.get("current_offer")),
            }
            for tracker in detail["tracker_rows"]
            for row in [tracker]
        ],
        "lastRefreshLabel": detail["tracker_refresh_footer_label"],
        "tripAnchorDate": trip_instance.anchor_date.isoformat(),
    }


def trip_editor_payload_for_new(
    snapshot,
    *,
    trip_kind: str,
    trip_group_id: str,
    unmatched_booking_id: str,
    trip_label: str,
) -> dict[str, object]:
    payload = new_trip_form_payload(
        snapshot,
        trip_kind=trip_kind,
        trip_group_id=trip_group_id,
        unmatched_booking_id=unmatched_booking_id,
        trip_label=trip_label,
    )
    return {
        **payload,
        "tripGroups": [
            {"value": group.trip_group_id, "label": group.label}
            for group in trip_groups(snapshot)
        ],
        "catalogs": json.loads(catalogs_json()),
    }


def trip_editor_payload_for_edit(
    snapshot,
    *,
    trip_id: str,
    trip_instance_id: str = "",
) -> dict[str, object]:
    payload = edit_trip_form_payload(snapshot, trip_id, trip_instance_id=trip_instance_id)
    return {
        **payload,
        "tripGroups": [
            {"value": group.trip_group_id, "label": group.label}
            for group in trip_groups(snapshot)
        ],
        "catalogs": json.loads(catalogs_json()),
    }
