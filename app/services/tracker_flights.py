from __future__ import annotations

from app.money import format_money
from app.route_options import stop_policy_allows_stops, time_in_window
from app.services.dashboard_trip_panels import tracker_context
from app.services.google_flights_fetcher import departure_time_from_offer_label
from app.services.itinerary_display import format_refresh_timestamp_label, format_time_range_label, travel_day_delta
from app.services.scheduled_trip_display import live_fare_offer_summary
from app.services.tracker_refresh_state import tracker_target_display_state


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

    price_records = repository.load_price_records_for_fetch_targets_at_times([
        (target.fetch_target_id, target.latest_fetched_at.isoformat())
        for _tracker, target in priced_entries
    ])
    target_by_id = {
        target.fetch_target_id: (tracker, target)
        for tracker, target in priced_entries
    }

    flight_rows: list[tuple[int, int, str, dict[str, object]]] = []
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
        flight_rows.append((
            effective_price,
            record.offer_rank,
            record.price_record_id,
            {
                "rowId": record.price_record_id,
                "travelDate": tracker.travel_date.isoformat(),
                "offer": offer,
            },
        ))

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
