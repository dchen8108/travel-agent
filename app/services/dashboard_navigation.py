from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.services.snapshot_queries import is_past_instance
from app.services.snapshots import AppSnapshot


def trip_focus_url(
    snapshot: AppSnapshot,
    trip_id: str,
    *,
    trip_instance_id: str | None = None,
) -> str:
    trip = next((item for item in snapshot.trips if item.trip_id == trip_id), None)
    if trip is None:
        return "/#all-travel"

    anchor = ""
    if trip_instance_id:
        trip_instance = next((item for item in snapshot.trip_instances if item.trip_instance_id == trip_instance_id), None)
        if not (trip_instance and is_past_instance(trip_instance)):
            anchor = f"scheduled-{trip_instance_id}"
    url = "/"
    if anchor:
        url = f"{url}#{anchor}"
    return url


def trip_panel_url(
    snapshot: AppSnapshot,
    trip_id: str,
    *,
    trip_instance_id: str,
    panel: str,
) -> str:
    base_url = trip_focus_url(snapshot, trip_id, trip_instance_id=trip_instance_id)
    parsed = urlsplit(base_url)
    params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {"panel", "trip_instance_id"}
    ]
    params.extend(
        [
            ("panel", panel),
            ("trip_instance_id", trip_instance_id),
        ]
    )
    anchor = parsed.fragment or f"scheduled-{trip_instance_id}"
    return urlunsplit(("", "", parsed.path or "/", urlencode(params, doseq=True), anchor))
