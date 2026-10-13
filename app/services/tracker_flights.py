from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.money import format_money
from app.route_options import stop_policy_allows_stops, time_in_window
from app.services.dashboard_trip_panels import tracker_context
from app.services.google_flights_fetcher import departure_time_from_offer_label
from app.services.itinerary_display import format_refresh_timestamp_label, format_time_range_label, travel_day_delta
from app.services.scheduled_trip_display import live_fare_offer_summary
from app.services.tracker_refresh_state import tracker_target_display_state


_LATEST_PRICE_RECORDS_CACHE_KEY = "latest_trip_flight_panel.price_records_by_target_time"
_PRICE_RECORD_LOOKUP_CHUNK_SIZE = 200


def _snapshot_cache(snapshot: object) -> dict[str, object]:
    cache = getattr(snapshot, "_query_cache", None)
    if cache is None:
        cache = {}
        setattr(snapshot, "_query_cache", cache)
    return cache


def _latest_price_record_pairs(snapshot) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for target in snapshot.tracker_fetch_targets:
        if (
            tracker_target_display_state(target, snapshot.app_state) == "priced"
            and target.latest_fetched_at is not None
        ):
            pairs.append((target.fetch_target_id, target.latest_fetched_at.isoformat()))
    return list(dict.fromkeys(pairs))


def _latest_price_records_by_target_time(snapshot, repository) -> dict[tuple[str, str], list[object]]:
    cache = _snapshot_cache(snapshot)
    cached = cache.get(_LATEST_PRICE_RECORDS_CACHE_KEY)
    if cached is not None:
        return cached  # type: ignore[return-value]

    records = []
    pairs = _latest_price_record_pairs(snapshot)
    for start in range(0, len(pairs), _PRICE_RECORD_LOOKUP_CHUNK_SIZE):
        records.extend(repository.load_price_records_for_fetch_targets_at_times(
            pairs[start:start + _PRICE_RECORD_LOOKUP_CHUNK_SIZE]
        ))

    grouped: dict[tuple[str, str], list[object]] = defaultdict(list)
    for record in records:
        observed_at = record.observed_at
        observed_at_key = observed_at.isoformat() if isinstance(observed_at, datetime) else str(observed_at)
        grouped[(record.fetch_target_id, observed_at_key)].append(record)
    cache[_LATEST_PRICE_RECORDS_CACHE_KEY] = dict(grouped)
    return cache[_LATEST_PRICE_RECORDS_CACHE_KEY]  # type: ignore[return-value]


def latest_trip_flight_panel(snapshot, repository, *, trip_instance_id: str) -> dict[str, object]:
    trip_instance, _parent_trip, trackers, tracker_targets = tracker_context(snapshot, trip_instance_id)
    target_entries = [
        (tracker, target)
        for tracker in trackers
        for target in tracker_targets.get(tracker.tracker_id, [])
    ]
    priced_entries = [
        (tracker, target)
        for tracker, target in target_entries
        if (
            tracker_target_display_state(target, snapshot.app_state) == "priced"
            and target.latest_fetched_at is not None
        )
    ]

    records_by_target_time = _latest_price_records_by_target_time(snapshot, repository)
    price_records = [
        record
        for _tracker, target in priced_entries
        for record in records_by_target_time.get((target.fetch_target_id, target.latest_fetched_at.isoformat()), [])
    ]
    target_by_id = {
        target.fetch_target_id: (tracker, target)
        for tracker, target in priced_entries
    }

    flight_rows_by_key: dict[tuple[object, ...], tuple[int, int, str, dict[str, object]]] = {}
    for record in price_records:
        tracker_target = target_by_id.get(record.fetch_target_id)
        if tracker_target is None:
            continue
        tracker, target = tracker_target
        if record.tracker_definition_signature != tracker.definition_signature:
            continue
        departure_time = departure_time_from_offer_label(record.departure_label)
        if not time_in_window(tracker.start_time, tracker.end_time, departure_time):
            continue
        if not stop_policy_allows_stops(tracker.stops, record.stops):
            continue
        effective_price = record.price + int(tracker.preference_bias_dollars or 0)
        offer = live_fare_offer_summary(
            anchor_date=trip_instance.anchor_date,
            travel_date=tracker.travel_date,
            detail=f"{record.query_origin_airport} \u2192 {record.query_destination_airport}",
            stops=record.stops,
            primary_meta_label=format_time_range_label(
                record.departure_label,
                record.arrival_label,
                fallback_day_delta=travel_day_delta(trip_instance.anchor_date, tracker.travel_date),
                anchor_date=trip_instance.anchor_date,
            ),
            meta_badges=[],
            airline_key=record.airline,
            price_label=format_money(record.price),
            href=target.google_flights_url if target.google_flights_url else "",
            tone="success",
            price_is_status=False,
        )
        row = (
            effective_price,
            record.offer_rank,
            record.price_record_id,
            {
                "rowId": record.price_record_id,
                "travelDate": tracker.travel_date.isoformat(),
                "offer": offer,
            },
        )
        display_key = (
            tracker.travel_date.isoformat(),
            offer["airline_key"],
            offer["detail"],
            offer["primary_meta_label"],
            offer["price_label"],
        )
        existing_row = flight_rows_by_key.get(display_key)
        if existing_row is None or row[:3] < existing_row[:3]:
            flight_rows_by_key[display_key] = row

    flight_rows = list(flight_rows_by_key.values())
    flight_rows.sort(key=lambda item: (item[0], item[1], item[2]))
    oldest_tracker_refresh_at = min(
        (
            target.last_fetch_finished_at
            for _tracker, target in target_entries
            if target.last_fetch_finished_at is not None
        ),
        default=None,
    )
    empty_label = "Checking live fares…" if (not flight_rows and any(
        tracker_target_display_state(target, snapshot.app_state) == "pending"
        for _tracker, target in target_entries
    )) else "No live fares right now."
    return {
        "rows": [row for *_meta, row in flight_rows],
        "lastRefreshLabel": (
            f"Last refresh · {format_refresh_timestamp_label(oldest_tracker_refresh_at)}"
            if oldest_tracker_refresh_at is not None
            else ""
        ),
        "tripAnchorDate": trip_instance.anchor_date.isoformat(),
        "emptyLabel": empty_label,
    }
