from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx

from app.models.base import FetchTargetStatus, TravelState, utcnow
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip_instance import TripInstance
from app.services.fetch_targets import FETCH_STAGGER_SECONDS, next_refresh_time
from app.services.google_flights_fetcher import (
    GoogleFlightsFetchError,
    GoogleFlightsNoResultsError,
    GoogleFlightsNoWindowMatchError,
    best_google_flights_offer,
    fetch_google_flights_offers,
    filter_google_flights_offers_by_departure_window,
)
from app.services.price_records import SuccessfulFetchRecord

MAX_FETCH_TARGETS_PER_RUN = 3
SLEEP_RANGE_SECONDS = (FETCH_STAGGER_SECONDS, FETCH_STAGGER_SECONDS + 3.0)


@dataclass(frozen=True)
class FetchBatchResult:
    fetched_count: int
    selected_count: int
    startup_jitter_applied_seconds: float
    updated_targets: list[TrackerFetchTarget]
    successful_fetches: list[SuccessfulFetchRecord]
    attempts: list["FetchAttemptResult"]


@dataclass(frozen=True)
class FetchAttemptResult:
    fetch_target_id: str
    tracker_id: str
    trip_instance_id: str
    origin_airport: str
    destination_airport: str
    travel_date: date | None
    tracker_rank: int | None
    status: str
    started_at: datetime
    fetched_at: datetime
    next_fetch_not_before: datetime | None
    duration_seconds: float
    price: int | None = None
    airline: str = ""
    offer_count: int = 0
    matching_offer_count: int = 0
    error: str = ""


def queue_rolling_refresh(
    trackers: list[Tracker],
    trip_instances: list[TripInstance],
    fetch_targets: list[TrackerFetchTarget],
    *,
    now: datetime | None = None,
    trip_instance_ids: set[str] | None = None,
    include_test_data: bool = True,
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
        if not include_test_data and (
            str(getattr(target, "data_scope", "live")) == "test"
            or str(getattr(tracker, "data_scope", "live")) == "test"
            or str(getattr(instance, "data_scope", "live")) == "test"
        ):
            continue
        if trip_instance_ids and target.trip_instance_id not in trip_instance_ids:
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
    include_test_data: bool = True,
) -> list[TrackerFetchTarget]:
    now = now or utcnow()
    if max_targets <= 0:
        return []
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
        if not include_test_data and (
            str(getattr(target, "data_scope", "live")) == "test"
            or str(getattr(tracker, "data_scope", "live")) == "test"
            or str(getattr(instance, "data_scope", "live")) == "test"
        ):
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
    startup_jitter_seconds: float = 0.0,
    due_targets: list[TrackerFetchTarget] | None = None,
    include_test_data: bool = True,
) -> FetchBatchResult:
    now = now or utcnow()
    if max_targets <= 0 and due_targets is None:
        return FetchBatchResult(
            fetched_count=0,
            selected_count=0,
            startup_jitter_applied_seconds=0.0,
            updated_targets=fetch_targets,
            successful_fetches=[],
            attempts=[],
        )
    tracker_by_id = {tracker.tracker_id: tracker for tracker in trackers}
    instance_by_id = {instance.trip_instance_id: instance for instance in trip_instances}
    if due_targets is None:
        due_targets = select_due_fetch_targets(
            trackers,
            trip_instances,
            fetch_targets,
            now=now,
            max_targets=max_targets,
            include_test_data=include_test_data,
        )
    if not due_targets:
        return FetchBatchResult(
            fetched_count=0,
            selected_count=0,
            startup_jitter_applied_seconds=0.0,
            updated_targets=fetch_targets,
            successful_fetches=[],
            attempts=[],
        )
    startup_jitter_applied_seconds = 0.0
    if startup_jitter_seconds > 0:
        startup_jitter_applied_seconds = random.uniform(0.0, startup_jitter_seconds)
        time.sleep(startup_jitter_applied_seconds)

    client = httpx.Client(timeout=20.0, follow_redirects=True)
    successful_fetches: list[SuccessfulFetchRecord] = []
    attempts: list[FetchAttemptResult] = []
    try:
        for index, target in enumerate(due_targets):
            tracker = tracker_by_id.get(target.tracker_id)
            instance = instance_by_id.get(target.trip_instance_id)
            if not tracker or not instance:
                continue
            if not include_test_data and (
                str(getattr(target, "data_scope", "live")) == "test"
                or str(getattr(tracker, "data_scope", "live")) == "test"
                or str(getattr(instance, "data_scope", "live")) == "test"
            ):
                continue
            fetch_started_at = utcnow()
            offers = []
            target.last_fetch_started_at = fetch_started_at
            target.updated_at = fetch_started_at
            try:
                offers = fetch_google_flights_offers(target.google_flights_url, client=client)
                fetched_at = utcnow()
                successful_fetches.append(
                    SuccessfulFetchRecord(
                        fetch_target_id=target.fetch_target_id,
                        fetched_at=fetched_at,
                        offers=list(offers),
                    )
                )
                matching_offers = filter_google_flights_offers_by_departure_window(
                    offers,
                    start_time=tracker.start_time,
                    end_time=tracker.end_time,
                )
                winner = best_google_flights_offer(matching_offers)
                if winner is None:
                    raise GoogleFlightsNoWindowMatchError("Flights were found, but none matched the exact departure window.")
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
                attempts.append(
                    FetchAttemptResult(
                        fetch_target_id=target.fetch_target_id,
                        tracker_id=target.tracker_id,
                        trip_instance_id=target.trip_instance_id,
                        origin_airport=target.origin_airport,
                        destination_airport=target.destination_airport,
                        travel_date=tracker.travel_date,
                        tracker_rank=tracker.rank,
                        status=FetchTargetStatus.SUCCESS,
                        started_at=fetch_started_at,
                        fetched_at=fetched_at,
                        next_fetch_not_before=target.next_fetch_not_before,
                        duration_seconds=(fetched_at - fetch_started_at).total_seconds(),
                        price=winner.price,
                        airline=winner.airline,
                        offer_count=len(offers),
                        matching_offer_count=len(matching_offers),
                    )
                )
            except GoogleFlightsNoResultsError as exc:
                no_results_at = utcnow()
                target.latest_price = None
                target.latest_airline = ""
                target.latest_departure_label = ""
                target.latest_arrival_label = ""
                target.latest_summary = ""
                target.latest_fetched_at = None
                target.last_fetch_finished_at = no_results_at
                target.last_fetch_status = FetchTargetStatus.NO_RESULTS
                target.last_fetch_error = str(exc)
                target.consecutive_failures = 0
                target.next_fetch_not_before = success_backoff_for_tracker(target, no_results_at)
                target.updated_at = no_results_at
                attempts.append(
                    FetchAttemptResult(
                        fetch_target_id=target.fetch_target_id,
                        tracker_id=target.tracker_id,
                        trip_instance_id=target.trip_instance_id,
                        origin_airport=target.origin_airport,
                        destination_airport=target.destination_airport,
                        travel_date=tracker.travel_date,
                        tracker_rank=tracker.rank,
                        status=FetchTargetStatus.NO_RESULTS,
                        started_at=fetch_started_at,
                        fetched_at=no_results_at,
                        next_fetch_not_before=target.next_fetch_not_before,
                        duration_seconds=(no_results_at - fetch_started_at).total_seconds(),
                        offer_count=len(offers),
                        matching_offer_count=0,
                        error=str(exc),
                    )
                )
            except GoogleFlightsNoWindowMatchError as exc:
                no_window_match_at = utcnow()
                target.latest_price = None
                target.latest_airline = ""
                target.latest_departure_label = ""
                target.latest_arrival_label = ""
                target.latest_summary = ""
                target.latest_fetched_at = None
                target.last_fetch_finished_at = no_window_match_at
                target.last_fetch_status = FetchTargetStatus.NO_WINDOW_MATCH
                target.last_fetch_error = str(exc)
                target.consecutive_failures = 0
                target.next_fetch_not_before = success_backoff_for_tracker(target, no_window_match_at)
                target.updated_at = no_window_match_at
                attempts.append(
                    FetchAttemptResult(
                        fetch_target_id=target.fetch_target_id,
                        tracker_id=target.tracker_id,
                        trip_instance_id=target.trip_instance_id,
                        origin_airport=target.origin_airport,
                        destination_airport=target.destination_airport,
                        travel_date=tracker.travel_date,
                        tracker_rank=tracker.rank,
                        status=FetchTargetStatus.NO_WINDOW_MATCH,
                        started_at=fetch_started_at,
                        fetched_at=no_window_match_at,
                        next_fetch_not_before=target.next_fetch_not_before,
                        duration_seconds=(no_window_match_at - fetch_started_at).total_seconds(),
                        offer_count=len(offers),
                        matching_offer_count=0,
                        error=str(exc),
                    )
                )
            except (GoogleFlightsFetchError, httpx.HTTPError) as exc:
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
                attempts.append(
                    FetchAttemptResult(
                        fetch_target_id=target.fetch_target_id,
                        tracker_id=target.tracker_id,
                        trip_instance_id=target.trip_instance_id,
                        origin_airport=target.origin_airport,
                        destination_airport=target.destination_airport,
                        travel_date=tracker.travel_date,
                        tracker_rank=tracker.rank,
                        status=FetchTargetStatus.FAILED,
                        started_at=fetch_started_at,
                        fetched_at=failed_at,
                        next_fetch_not_before=target.next_fetch_not_before,
                        duration_seconds=(failed_at - fetch_started_at).total_seconds(),
                        offer_count=len(offers),
                        error=str(exc),
                    )
                )
            if sleep_between_requests and index < len(due_targets) - 1:
                time.sleep(random.uniform(*SLEEP_RANGE_SECONDS))
    finally:
        client.close()

    return FetchBatchResult(
        fetched_count=len(due_targets),
        selected_count=len(due_targets),
        startup_jitter_applied_seconds=startup_jitter_applied_seconds,
        updated_targets=fetch_targets,
        successful_fetches=successful_fetches,
        attempts=attempts,
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
) -> tuple[int, date, datetime, int, str, str]:
    instance = instance_by_id.get(target.trip_instance_id)
    tracker = tracker_by_id.get(target.tracker_id)
    travel_date = tracker.travel_date if tracker else (instance.anchor_date if instance else date.max)
    last_finished = target.last_fetch_finished_at or datetime(1970, 1, 1).astimezone()
    rank = tracker.rank if tracker else 999
    initialization_priority = 0 if target.latest_price is None else 1
    return (
        initialization_priority,
        travel_date,
        last_finished,
        rank,
        target.origin_airport,
        target.destination_airport,
    )
