from __future__ import annotations

from datetime import date

from app.services.frontend_api import dashboard_payload


def _trip_state(row: dict[str, object]) -> str:
    trip = row.get("trip")
    if isinstance(trip, dict) and bool(trip.get("skipped")):
        return "skipped"
    if row.get("bookedOffer") is not None:
        return "booked"
    return "planning"


def _trip_date(row: dict[str, object]) -> date:
    trip = row.get("trip")
    if not isinstance(trip, dict):
        raise ValueError("Trip row is missing trip identity data.")
    return date.fromisoformat(str(trip["anchorDate"]))


def v2_workspace_payload(
    snapshot,
    *,
    today: date,
    repository=None,
) -> dict[str, object]:
    """Build the stable, read-only contract for the parallel v2 experience."""
    canonical = dashboard_payload(
        snapshot,
        today=today,
        selected_trip_group_ids=[],
        include_booked=True,
        include_skipped=True,
        repository=repository,
    )
    trip_items = []
    for row in canonical["trips"]:
        trip_date = _trip_date(row)
        trip_items.append(
            {
                "state": _trip_state(row),
                "daysUntil": (trip_date - today).days,
                "row": row,
            }
        )

    next_two_weeks = [item for item in trip_items if 0 <= item["daysUntil"] <= 14]
    return {
        "version": 2,
        "today": today.isoformat(),
        "horizonWeeks": int(snapshot.app_state.future_weeks),
        "stats": {
            "attentionCount": len(canonical["actionItems"]),
            "departuresNext14Days": len(next_two_weeks),
            "bookedNext14Days": sum(item["state"] == "booked" for item in next_two_weeks),
            "trackedTrips": sum(item["row"].get("currentOffer") is not None for item in trip_items),
        },
        "attentionItems": canonical["actionItems"],
        "trips": trip_items,
        "collections": canonical["collections"],
    }
