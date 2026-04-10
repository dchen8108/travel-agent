from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx

from app.models.base import AppState, FetchTargetStatus, utcnow
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip_instance import TripInstance
from app.services.fetch_targets import fetch_stagger_seconds
from app.services.google_flights_fetcher import (
    GoogleFlightsFetchError,
    GoogleFlightsNoResultsError,
    GoogleFlightsNoWindowMatchError,
    best_google_flights_offer,
    fetch_google_flights_offers,
    filter_google_flights_offers_by_departure_window,
)
from app.services.price_records import SuccessfulFetchRecord
from app.storage.repository import Repository

def _app_state(app_state: AppState | None) -> AppState:
    return app_state or AppState()


def fetch_max_targets_per_run(app_state: AppState | None = None) -> int:
    return _app_state(app_state).fetch_max_targets_per_run


def fetch_sleep_range_seconds(app_state: AppState | None = None) -> tuple[float, float]:
    state = _app_state(app_state)
    stagger_seconds = fetch_stagger_seconds(state)
    return (
        float(stagger_seconds),
        float(stagger_seconds + state.fetch_request_sleep_max_extra_seconds),
    )


def fetch_target_claim_lease(app_state: AppState | None = None) -> timedelta:
    return timedelta(minutes=_app_state(app_state).fetch_claim_lease_minutes)


def fetch_request_timeout_seconds(app_state: AppState | None = None) -> float:
    return _app_state(app_state).fetch_request_timeout_seconds


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
    app_state: AppState | None = None,
) -> int:
    now = now or utcnow()
    queued_count = 0
    tracker_by_id = {tracker.tracker_id: tracker for tracker in trackers}
    instance_by_id = {instance.trip_instance_id: instance for instance in trip_instances}
    for target in fetch_targets:
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
        if instance.deleted or tracker.travel_date < now.date():
            continue
        target.refresh_requested_at = now
        target.updated_at = now
        queued_count += 1
    return queued_count


def claim_due_fetch_targets(
    repository: Repository,
    *,
    run_id: str,
    now: datetime | None = None,
    max_targets: int | None = None,
    include_test_data: bool = True,
    lease_duration: timedelta | None = None,
    app_state: AppState | None = None,
) -> list[str]:
    now = now or utcnow()
    max_targets = fetch_max_targets_per_run(app_state) if max_targets is None else max_targets
    lease_duration = fetch_target_claim_lease(app_state) if lease_duration is None else lease_duration
    if max_targets <= 0:
        return []
    with repository.transaction():
        trackers = repository.load_trackers()
        trip_instances = repository.load_trip_instances()
        fetch_targets = repository.load_tracker_fetch_targets()
        due_targets = select_due_fetch_targets(
            trackers,
            trip_instances,
            fetch_targets,
            now=now,
            max_targets=max_targets,
            include_test_data=include_test_data,
            app_state=app_state,
        )
        if not due_targets:
            return []
        claimed_until = now + lease_duration
        for target in due_targets:
            target.fetch_claim_owner = run_id
            target.fetch_claim_expires_at = claimed_until
            target.updated_at = now
        repository.upsert_tracker_fetch_targets(due_targets)
        return [target.fetch_target_id for target in due_targets]


def select_due_fetch_targets(
    trackers: list[Tracker],
    trip_instances: list[TripInstance],
    fetch_targets: list[TrackerFetchTarget],
    *,
    now: datetime | None = None,
    max_targets: int | None = None,
    include_test_data: bool = True,
    app_state: AppState | None = None,
) -> list[TrackerFetchTarget]:
    now = now or utcnow()
    max_targets = fetch_max_targets_per_run(app_state) if max_targets is None else max_targets
    if max_targets <= 0:
        return []
    tracker_by_id = {tracker.tracker_id: tracker for tracker in trackers}
    instance_by_id = {instance.trip_instance_id: instance for instance in trip_instances}
    selected: list[TrackerFetchTarget] = []
    ordered = sorted(
        fetch_targets,
        key=lambda item: _selection_sort_key(item, tracker_by_id, instance_by_id, now),
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
        if instance.deleted or tracker.travel_date < now.date():
            continue
        if _has_active_claim(target, now):
            continue
        if _has_failure_backoff(target, now, app_state=app_state):
            continue
        selected.append(target)
        if len(selected) >= max_targets:
            break
    return selected


def run_fetch_batch(
    trackers: list[Tracker],
    trip_instances: list[TripInstance],
    fetch_targets: list[TrackerFetchTarget],
    *,
    now: datetime | None = None,
    max_targets: int | None = None,
    sleep_between_requests: bool = True,
    startup_jitter_seconds: float = 0.0,
    due_targets: list[TrackerFetchTarget] | None = None,
    include_test_data: bool = True,
    app_state: AppState | None = None,
) -> FetchBatchResult:
    now = now or utcnow()
    max_targets = fetch_max_targets_per_run(app_state) if max_targets is None else max_targets
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
            app_state=app_state,
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

    client = httpx.Client(timeout=fetch_request_timeout_seconds(app_state), follow_redirects=True)
    successful_fetches: list[SuccessfulFetchRecord] = []
    attempts: list[FetchAttemptResult] = []
    try:
        for index, target in enumerate(due_targets):
            tracker = tracker_by_id.get(target.tracker_id)
            instance = instance_by_id.get(target.trip_instance_id)
            if not tracker or not instance:
                _release_fetch_claim(target)
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
                target.refresh_requested_at = None
                _release_fetch_claim(target)
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
                target.refresh_requested_at = None
                _release_fetch_claim(target)
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
                target.refresh_requested_at = None
                _release_fetch_claim(target)
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
                target.refresh_requested_at = None
                _release_fetch_claim(target)
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
                        duration_seconds=(failed_at - fetch_started_at).total_seconds(),
                        offer_count=len(offers),
                        error=str(exc),
                    )
                )
            if sleep_between_requests and index < len(due_targets) - 1:
                time.sleep(random.uniform(*fetch_sleep_range_seconds(app_state)))
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
def failure_backoff(consecutive_failures: int, *, app_state: AppState | None = None) -> timedelta:
    state = _app_state(app_state)
    if consecutive_failures <= 1:
        return timedelta(hours=state.fetch_failure_backoff_hours_first)
    if consecutive_failures == 2:
        return timedelta(hours=state.fetch_failure_backoff_hours_second)
    return timedelta(hours=state.fetch_failure_backoff_hours_repeated)


def _has_active_claim(target: TrackerFetchTarget, now: datetime) -> bool:
    return bool(target.fetch_claim_expires_at and target.fetch_claim_expires_at > now)


def _has_failure_backoff(
    target: TrackerFetchTarget,
    now: datetime,
    *,
    app_state: AppState | None = None,
) -> bool:
    if target.refresh_requested_at is not None:
        return False
    if target.last_fetch_status != FetchTargetStatus.FAILED:
        return False
    if target.last_fetch_finished_at is None:
        return False
    return target.last_fetch_finished_at + failure_backoff(
        target.consecutive_failures,
        app_state=app_state,
    ) > now


def _release_fetch_claim(target: TrackerFetchTarget) -> None:
    target.fetch_claim_owner = ""
    target.fetch_claim_expires_at = None


def _selection_sort_key(
    target: TrackerFetchTarget,
    tracker_by_id: dict[str, Tracker],
    instance_by_id: dict[str, TripInstance],
    now: datetime,
) -> tuple[int, datetime, int, datetime, date, int, str, str]:
    instance = instance_by_id.get(target.trip_instance_id)
    tracker = tracker_by_id.get(target.tracker_id)
    travel_date = tracker.travel_date if tracker else (instance.anchor_date if instance else date.max)
    request_time = target.refresh_requested_at or datetime(9999, 12, 31, tzinfo=now.tzinfo)
    last_finished = target.last_fetch_finished_at or datetime(1970, 1, 1, tzinfo=now.tzinfo)
    rank = tracker.rank if tracker else 999
    refresh_request_priority = 0 if target.refresh_requested_at is not None else 1
    initialization_priority = 0 if target.last_fetch_finished_at is None else 1
    return (
        refresh_request_priority,
        request_time,
        initialization_priority,
        last_finished,
        travel_date,
        rank,
        target.origin_airport,
        target.destination_airport,
    )
