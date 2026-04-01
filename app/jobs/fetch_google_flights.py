from __future__ import annotations

import argparse

from app.services.background_fetch import run_fetch_batch
from app.services.price_records import build_price_records
from app.services.recommendations import apply_fetch_target_rollups, recompute_trip_states
from app.services.workflows import sync_and_persist
from app.settings import get_settings
from app.storage.repository import Repository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-targets", type=int, default=3)
    parser.add_argument("--no-sleep", action="store_true")
    args = parser.parse_args()

    repository = Repository(get_settings())
    snapshot = sync_and_persist(repository)
    if not snapshot.app_state.enable_background_fetcher:
        print("Background Google Flights fetcher disabled.")
        return

    result = run_fetch_batch(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=args.max_targets,
        sleep_between_requests=not args.no_sleep,
    )
    apply_fetch_target_rollups(snapshot.trackers, snapshot.tracker_fetch_targets)
    recompute_trip_states(snapshot.trip_instances, snapshot.trackers, snapshot.bookings)
    price_records = build_price_records(
        trips=snapshot.trips,
        trip_instances=snapshot.trip_instances,
        trackers=snapshot.trackers,
        fetch_targets=snapshot.tracker_fetch_targets,
        successful_fetches=result.successful_fetches,
    )

    repository.append_price_records(price_records)
    repository.save_tracker_fetch_targets(snapshot.tracker_fetch_targets)
    repository.save_trackers(snapshot.trackers)
    repository.save_trip_instances(snapshot.trip_instances)
    print(f"Fetched {result.fetched_count} Google Flights target(s).")


if __name__ == "__main__":
    main()
