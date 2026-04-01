from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

from app.models.base import utcnow
from app.services.background_fetch import run_fetch_batch, select_due_fetch_targets
from app.services.dashboard import trip_for_instance
from app.services.ids import new_id
from app.services.price_records import build_price_records
from app.services.recommendations import apply_fetch_target_rollups, recompute_trip_states
from app.services.workflows import sync_and_persist
from app.settings import get_settings
from app.storage.repository import Repository

DEFAULT_STARTUP_JITTER_SECONDS = 8.0


def _emit_log(event: str, *, stream=sys.stdout, **fields: object) -> None:
    payload = {
        "timestamp": utcnow().isoformat(),
        "event": event,
        **fields,
    }
    print(json.dumps(payload, sort_keys=True, default=str), file=stream, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-targets", type=int, default=3)
    parser.add_argument("--no-sleep", action="store_true")
    parser.add_argument("--startup-jitter-seconds", type=float, default=DEFAULT_STARTUP_JITTER_SECONDS)
    args = parser.parse_args()

    repository = Repository(get_settings())
    run_id = new_id("fetchrun")
    stage = "sync"
    selected_target_ids: list[str] = []
    total_due_target_count = 0
    try:
        snapshot = sync_and_persist(repository)
        if not snapshot.app_state.enable_background_fetcher:
            _emit_log("run_disabled", run_id=run_id, pid=os.getpid())
            return

        selection_now = utcnow()
        all_due_targets = select_due_fetch_targets(
            snapshot.trackers,
            snapshot.trip_instances,
            snapshot.tracker_fetch_targets,
            now=selection_now,
            max_targets=len(snapshot.tracker_fetch_targets),
        )
        due_targets = select_due_fetch_targets(
            snapshot.trackers,
            snapshot.trip_instances,
            snapshot.tracker_fetch_targets,
            now=selection_now,
            max_targets=args.max_targets,
        )
        selected_target_ids = [target.fetch_target_id for target in due_targets]
        total_due_target_count = len(all_due_targets)
        _emit_log(
            "run_started",
            run_id=run_id,
            pid=os.getpid(),
            max_targets=args.max_targets,
            sleep_between_requests=not args.no_sleep,
            startup_jitter_seconds=max(args.startup_jitter_seconds, 0.0),
            total_trackers=len(snapshot.trackers),
            total_fetch_targets=len(snapshot.tracker_fetch_targets),
            total_due_target_count=total_due_target_count,
            selected_target_count=len(due_targets),
            selected_fetch_target_ids=selected_target_ids,
        )

        stage = "fetch"
        result = run_fetch_batch(
            snapshot.trackers,
            snapshot.trip_instances,
            snapshot.tracker_fetch_targets,
            now=selection_now,
            max_targets=args.max_targets,
            sleep_between_requests=not args.no_sleep,
            startup_jitter_seconds=max(args.startup_jitter_seconds, 0.0),
            due_targets=due_targets,
        )
        trip_label_by_instance_id = {}
        for instance in snapshot.trip_instances:
            trip = trip_for_instance(snapshot, instance.trip_instance_id)
            trip_label_by_instance_id[instance.trip_instance_id] = trip.label if trip else instance.display_label
        target_by_id = {target.fetch_target_id: target for target in snapshot.tracker_fetch_targets}
        for attempt in result.attempts:
            target = target_by_id.get(attempt.fetch_target_id)
            _emit_log(
                "target_processed",
                run_id=run_id,
                fetch_target_id=attempt.fetch_target_id,
                tracker_id=attempt.tracker_id,
                trip_instance_id=attempt.trip_instance_id,
                trip_label=trip_label_by_instance_id.get(attempt.trip_instance_id, ""),
                tracker_rank=attempt.tracker_rank,
                origin_airport=attempt.origin_airport,
                destination_airport=attempt.destination_airport,
                travel_date=attempt.travel_date.isoformat() if attempt.travel_date else "",
                status=str(attempt.status),
                started_at=attempt.started_at.isoformat(),
                completed_at=attempt.fetched_at.isoformat(),
                duration_seconds=round(attempt.duration_seconds, 3),
                price=attempt.price,
                airline=attempt.airline,
                offer_count=attempt.offer_count,
                matching_offer_count=attempt.matching_offer_count,
                next_refresh_at=attempt.next_fetch_not_before.isoformat() if attempt.next_fetch_not_before else "",
                google_flights_url=target.google_flights_url if target else "",
                error=attempt.error,
            )

        stage = "persist"
        apply_fetch_target_rollups(snapshot.trackers, snapshot.tracker_fetch_targets)
        recompute_trip_states(snapshot.trip_instances, snapshot.trackers, snapshot.bookings)
        price_records = build_price_records(
            trips=snapshot.trips,
            trip_instances=snapshot.trip_instances,
            trackers=snapshot.trackers,
            fetch_targets=snapshot.tracker_fetch_targets,
            successful_fetches=result.successful_fetches,
        )

        with repository.transaction():
            repository.append_price_records(price_records)
            repository.save_tracker_fetch_targets(snapshot.tracker_fetch_targets)
            repository.save_trackers(snapshot.trackers)
            repository.save_trip_instances(snapshot.trip_instances)
        status_counts: dict[str, int] = {}
        for attempt in result.attempts:
            key = str(attempt.status)
            status_counts[key] = status_counts.get(key, 0) + 1
        _emit_log(
            "run_completed",
            run_id=run_id,
            pid=os.getpid(),
            total_due_target_count=total_due_target_count,
            selected_target_count=result.selected_count,
            processed_target_count=len(result.attempts),
            startup_jitter_applied_seconds=round(result.startup_jitter_applied_seconds, 3),
            successful_fetch_count=len(result.successful_fetches),
            price_record_count=len(price_records),
            status_counts=status_counts,
        )
    except Exception as exc:
        _emit_log(
            "run_failed",
            stream=sys.stderr,
            run_id=run_id,
            pid=os.getpid(),
            stage=stage,
            selected_fetch_target_ids=selected_target_ids,
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        raise


if __name__ == "__main__":
    main()
