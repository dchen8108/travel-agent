from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from app.models.base import AppState, FetchTargetStatus, utcnow
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget

TrackerTargetDisplayState = Literal["priced", "unavailable", "pending"]


def tracker_refresh_cutoff(app_state: AppState, *, now: datetime | None = None) -> datetime:
    current = now.astimezone() if now is not None else utcnow()
    return current - timedelta(hours=app_state.tracker_freshness_window_hours)


def tracker_has_fresh_price(
    tracker: Tracker,
    app_state: AppState,
    *,
    now: datetime | None = None,
) -> bool:
    cutoff = tracker_refresh_cutoff(app_state, now=now)
    return (
        tracker.latest_observed_price is not None
        and tracker.latest_fetched_at is not None
        and tracker.latest_fetched_at >= cutoff
    )


def tracker_target_display_state(
    target: TrackerFetchTarget,
    app_state: AppState,
    *,
    now: datetime | None = None,
) -> TrackerTargetDisplayState:
    cutoff = tracker_refresh_cutoff(app_state, now=now)
    if (
        target.latest_price is not None
        and target.latest_fetched_at is not None
        and target.latest_fetched_at >= cutoff
    ):
        return "priced"
    if (
        target.last_fetch_status in {FetchTargetStatus.NO_RESULTS, FetchTargetStatus.NO_WINDOW_MATCH}
        and target.last_fetch_finished_at is not None
        and target.last_fetch_finished_at >= cutoff
    ):
        return "unavailable"
    return "pending"
