from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx

from app.models.base import FetchTargetStatus, TrackerStatus, TravelState, utcnow
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip_instance import TripInstance
from app.services.fetch_targets import FETCH_STAGGER_SECONDS, next_refresh_time
from app.services.google_flights_fetcher import (
    GoogleFlightsFetchError,
    best_google_flights_offer,
    fetch_google_flights_offers,
)
from app.services.price_records import SuccessfulFetchRecord

MAX_FETCH_TARGETS_PER_RUN = 3
SLEEP_RANGE_SECONDS = (FETCH_STAGGER_SECONDS, FETCH_STAGGER_SECONDS + 3.0)


@dataclass(frozen=True)
class FetchBatchResult:
    fetched_count: int
    updated_targets: list[TrackerFetchTarget]
    successful_fetches: list[SuccessfulFetchRecord]


def queue_rolling_refresh(
    trackers: list[Tracker],
    trip_instances: list[TripInstance],
    fetch_targets: list[TrackerFetchTarget],
    *,
    now: datetime | None = None,
) -> int:
    now = now or utcnow()
    tracker_by_id = {tracker.tracker_id: tracker for tracker in trackers}
    instance_by_id = {instance.trip_instance_id: instance for instance in trip_instances}
    ordered = sorted(
        fetch_targets,
        key=lambda item: _selection_sort_key(item, tracker_by_id, instance_by_id, now.date()),
    )
    queued_count = 0
    next_scheduled_at = now
    for target in ordered:
        tracker = tracker_by_id.get(target.tracker_id)
        instance = instance_by_id.get(target.trip_instance_id)
        if not tracker or not instance:
            continue
        if instance.travel_state == TravelState.SKIPPED or tracker.travel_date < now.date():
            continue
        target.next_fetch_not_before = next_scheduled_at
        target.updated_at = now
        queued_count += 1
        next_scheduled_at = next_scheduled_at + timedelta(seconds=FETCH_STAGGER_SECONDS)
    return queued_count


def select_due_fetch_targets(
    trackers: list[Tracker],
    trip_instances: list[TripInstance],
    fetch_targets: list[TrackerFetchTarget],
    *,
    now: datetime | None = None,
    max_targets: int = MAX_FETCH_TARGETS_PER_RUN,
) -> list[TrackerFetchTarget]:
    now = now or utcnow()
    tracker_by_id = {tracker.tracker_id: tracker for tracker in trackers}
    instance_by_id = {instance.trip_instance_id: instance for instance in trip_instances}
    selected: list[TrackerFetchTarget] = []
    selected_tracker_ids: set[str] = set()

    ordered = sorted(
        fetch_targets,
        key=lambda item: _selection_sort_key(item, tracker_by_id, instance_by_id, now.date()),
    )
    for target in ordered:
        tracker = tracker_by_id.get(target.tracker_id)
        instance = instance_by_id.get(target.trip_instance_id)
        if not tracker or not instance:
            continue
        if instance.travel_state == TravelState.SKIPPED or tracker.travel_date < now.date():
            continue
        if target.next_fetch_not_before and target.next_fetch_not_before > now:
            continue
        if target.tracker_id in selected_tracker_ids:
            continue
        selected.append(target)
        selected_tracker_ids.add(target.tracker_id)
        if len(selected) >= max_targets:
            break
    return selected


def run_fetch_batch(
    trackers: list[Tracker],
    trip_instances: list[TripInstance],
    fetch_targets: list[TrackerFetchTarget],
    *,
    now: datetime | None = None,
    max_targets: int = MAX_FETCH_TARGETS_PER_RUN,
    sleep_between_requests: bool = True,
) -> FetchBatchResult:
    now = now or utcnow()
    tracker_by_id = {tracker.tracker_id: tracker for tracker in trackers}
    instance_by_id = {instance.trip_instance_id: instance for instance in trip_instances}
    due_targets = select_due_fetch_targets(
        trackers,
        trip_instances,
        fetch_targets,
        now=now,
        max_targets=max_targets,
    )
    if not due_targets:
        return FetchBatchResult(fetched_count=0, updated_targets=fetch_targets, successful_fetches=[])

    client = httpx.Client(timeout=20.0, follow_redirects=True)
    successful_fetches: list[SuccessfulFetchRecord] = []
    try:
        for index, target in enumerate(due_targets):
            tracker = tracker_by_id.get(target.tracker_id)
            instance = instance_by_id.get(target.trip_instance_id)
            if not tracker or not instance:
                continue
            fetch_started_at = utcnow()
            target.last_fetch_started_at = fetch_started_at
            target.updated_at = fetch_started_at
            try:
                offers = fetch_google_flights_offers(target.google_flights_url, client=client)
                winner = best_google_flights_offer(offers)
                if winner is None:
                    raise GoogleFlightsFetchError("No usable offers found.")
                fetched_at = utcnow()
                successful_fetches.append(
                    SuccessfulFetchRecord(
                        fetch_target_id=target.fetch_target_id,
                        fetched_at=fetched_at,
                        offers=list(offers),
                    )
                )
                target.latest_price = winner.price
                target.latest_airline = winner.airline
                target.latest_departure_label = winner.departure_label
                target.latest_arrival_label = winner.arrival_label
                target.latest_summary = winner.summary
                target.latest_fetched_at = fetched_at
                target.last_fetch_finished_at = fetched_at
                target.last_fetch_status = FetchTargetStatus.SUCCESS
                target.last_fetch_error = ""
                target.consecutive_failures = 0
                target.next_fetch_not_before = success_backoff_for_tracker(target, fetched_at)
                target.updated_at = fetched_at
            except Exception as exc:
                failed_at = utcnow()
                target.last_fetch_finished_at = failed_at
                target.last_fetch_status = FetchTargetStatus.FAILED
                target.last_fetch_error = str(exc)
                target.consecutive_failures += 1
                target.next_fetch_not_before = max(
                    next_refresh_time(failed_at, target.schedule_offset_seconds),
                    failed_at + failure_backoff(target.consecutive_failures),
                )
                target.updated_at = failed_at
            if sleep_between_requests and index < len(due_targets) - 1:
                time.sleep(random.uniform(*SLEEP_RANGE_SECONDS))
    finally:
        client.close()

    return FetchBatchResult(
        fetched_count=len(due_targets),
        updated_targets=fetch_targets,
        successful_fetches=successful_fetches,
    )


def success_backoff_for_tracker(target: TrackerFetchTarget, fetched_at: datetime) -> datetime:
    return next_refresh_time(fetched_at, target.schedule_offset_seconds)


def failure_backoff(consecutive_failures: int) -> timedelta:
    if consecutive_failures <= 1:
        return timedelta(hours=12)
    if consecutive_failures == 2:
        return timedelta(hours=24)
    return timedelta(hours=48)


def _selection_sort_key(
    target: TrackerFetchTarget,
    tracker_by_id: dict[str, Tracker],
    instance_by_id: dict[str, TripInstance],
    today: date,
) -> tuple[date, datetime, int, str, str]:
    instance = instance_by_id.get(target.trip_instance_id)
    tracker = tracker_by_id.get(target.tracker_id)
    travel_date = tracker.travel_date if tracker else (instance.anchor_date if instance else date.max)
    last_finished = target.last_fetch_finished_at or datetime(1970, 1, 1).astimezone()
    rank = tracker.rank if tracker else 999
    return (
        travel_date,
        last_finished,
        rank,
        target.origin_airport,
        target.destination_airport,
    )
