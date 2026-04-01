from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.background_fetch import queue_rolling_refresh
from app.services.google_flights import generated_tracker_seed_summary
from app.services.dashboard import (
    best_tracker,
    fetch_targets_for_tracker,
    load_snapshot,
    trackers_for_instance,
    trip_focus_url,
)
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository
from app.web import base_context, get_repository, get_templates

router = APIRouter(tags=["trackers"])

def _format_tracker_timestamp(value) -> str:
    if value is None:
        return "Not yet"
    hour = value.strftime("%I").lstrip("0") or "12"
    return f"{value.strftime('%b %d')}, {hour}:{value.strftime('%M %p')}"


def _tracker_monitor_state(tracker, fetch_targets) -> dict[str, object]:
    last_finished_at = max(
        (target.last_fetch_finished_at for target in fetch_targets if target.last_fetch_finished_at),
        default=None,
    )
    next_refresh_at = min(
        (target.next_fetch_not_before for target in fetch_targets if target.next_fetch_not_before),
        default=None,
    )
    failed_targets = [target for target in fetch_targets if target.last_fetch_status == "failed"]
    if tracker.latest_observed_price is not None:
        return {
            "last_updated_at": tracker.last_signal_at or last_finished_at,
            "next_refresh_at": next_refresh_at,
            "is_retrying": bool(failed_targets),
        }
    if failed_targets:
        return {
            "last_updated_at": last_finished_at,
            "next_refresh_at": next_refresh_at,
            "is_retrying": True,
        }
    return {
        "last_updated_at": last_finished_at,
        "next_refresh_at": next_refresh_at,
        "is_retrying": False,
    }


@router.get("/trackers", response_class=HTMLResponse)
def trackers_index(
    request: Request,
    repository: Repository = Depends(get_repository),
) -> HTMLResponse:
    snapshot = load_snapshot(repository)
    today = date.today()
    grouped: dict[str, list] = defaultdict(list)
    trip_instances_by_id = {item.trip_instance_id: item for item in snapshot.trip_instances}
    for tracker in snapshot.trackers:
        trip_instance = trip_instances_by_id.get(tracker.trip_instance_id)
        if trip_instance is None or trip_instance.anchor_date < today:
            continue
        grouped[tracker.trip_instance_id].append(tracker)
    ordered_groups = [
        (trip_instances_by_id[trip_instance_id], sorted(trackers, key=lambda item: item.rank))
        for trip_instance_id, trackers in sorted(
            grouped.items(),
            key=lambda item: (trip_instances_by_id[item[0]].anchor_date, trip_instances_by_id[item[0]].display_label),
        )
    ]
    tracker_monitor_by_id = {}
    for _, trackers in ordered_groups:
        for tracker in trackers:
            tracker_monitor_by_id[tracker.tracker_id] = _tracker_monitor_state(
                tracker,
                fetch_targets_for_tracker(snapshot, tracker.tracker_id),
            )
    return get_templates(request).TemplateResponse(
        request=request,
        name="trackers.html",
        context=base_context(
            request,
            page="trackers",
            snapshot=snapshot,
            ordered_groups=ordered_groups,
            best_tracker=best_tracker,
            fetch_targets_for_tracker=fetch_targets_for_tracker,
            trackers_for_instance=trackers_for_instance,
            trip_focus_url=trip_focus_url,
            generated_tracker_seed_summary=generated_tracker_seed_summary,
            tracker_monitor_by_id=tracker_monitor_by_id,
            format_tracker_timestamp=_format_tracker_timestamp,
        ),
    )


@router.post("/trackers/queue-refresh")
def queue_tracker_refresh(
    repository: Repository = Depends(get_repository),
) -> RedirectResponse:
    snapshot = sync_and_persist(repository)
    queued_count = queue_rolling_refresh(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
    )
    repository.save_tracker_fetch_targets(snapshot.tracker_fetch_targets)
    if queued_count == 0:
        message = "Nothing+to+refresh+yet."
    elif queued_count == 1:
        message = "Refresh+queued+for+1+airport-pair+search."
    else:
        message = f"Refresh+queued+for+{queued_count}+airport-pair+searches."
    return RedirectResponse(url=f"/trackers?message={message}", status_code=303)
