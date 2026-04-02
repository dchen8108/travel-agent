from __future__ import annotations

from collections import defaultdict

from app.models.base import TravelState, utcnow
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.route_options import cumulative_route_option_bias, travel_date_for_offset
from app.services.ids import stable_id


def tracker_definition_signature(
    *,
    rank: int,
    origin_airports: str,
    destination_airports: str,
    airlines: str,
    day_offset: int,
    travel_date,
    start_time: str,
    end_time: str,
    fare_class_policy: str,
) -> str:
    return stable_id(
        "trkdef",
        rank,
        origin_airports,
        destination_airports,
        airlines,
        day_offset,
        travel_date.isoformat(),
        start_time,
        end_time,
        fare_class_policy,
    )


def reconcile_trackers(
    trips: list[Trip],
    trip_instances: list[TripInstance],
    route_options: list[RouteOption],
    existing_trackers: list[Tracker],
) -> list[Tracker]:
    trip_by_id = {trip.trip_id: trip for trip in trips}
    route_options_by_trip: dict[str, list[RouteOption]] = defaultdict(list)
    for option in route_options:
        route_options_by_trip[option.trip_id].append(option)
    for options in route_options_by_trip.values():
        options.sort(key=lambda item: item.rank)

    existing_by_id = {tracker.tracker_id: tracker for tracker in existing_trackers}
    desired: list[Tracker] = []
    desired_ids: set[str] = set()

    for instance in trip_instances:
        if instance.travel_state == TravelState.SKIPPED:
            continue
        trip = trip_by_id.get(instance.trip_id)
        if trip is not None and trip.trip_kind == "one_time" and not trip.active:
            continue
        options = route_options_by_trip.get(instance.trip_id, [])
        pairwise_biases = [option.savings_needed_vs_previous for option in options]
        for option in options:
            tracker_id = stable_id("trk", instance.trip_instance_id, option.route_option_id)
            desired_ids.add(tracker_id)
            travel_date = travel_date_for_offset(instance.anchor_date, option.day_offset)
            preference_bias_dollars = (
                cumulative_route_option_bias(pairwise_biases, option.rank - 1)
                if trip and trip.preference_mode == "ranked_bias"
                else 0
            )
            definition_signature = tracker_definition_signature(
                rank=option.rank,
                origin_airports=option.origin_airports,
                destination_airports=option.destination_airports,
                airlines=option.airlines,
                day_offset=option.day_offset,
                travel_date=travel_date,
                start_time=option.start_time,
                end_time=option.end_time,
                fare_class_policy=option.fare_class_policy,
            )
            existing = existing_by_id.get(tracker_id)
            if existing:
                definition_changed = bool(existing.definition_signature) and existing.definition_signature != definition_signature
                existing.rank = option.rank
                existing.data_scope = instance.data_scope
                existing.preference_bias_dollars = preference_bias_dollars
                existing.origin_airports = option.origin_airports
                existing.destination_airports = option.destination_airports
                existing.airlines = option.airlines
                existing.day_offset = option.day_offset
                existing.travel_date = travel_date
                existing.start_time = option.start_time
                existing.end_time = option.end_time
                existing.fare_class_policy = option.fare_class_policy
                existing.definition_signature = definition_signature
                if definition_changed:
                    existing.last_signal_at = None
                    existing.latest_observed_price = None
                    existing.latest_fetched_at = None
                    existing.latest_winning_origin_airport = ""
                    existing.latest_winning_destination_airport = ""
                    existing.latest_signal_source = ""
                    existing.latest_match_summary = ""
                existing.updated_at = utcnow()
                desired.append(existing)
                continue
            desired.append(
                Tracker(
                    tracker_id=tracker_id,
                    trip_instance_id=instance.trip_instance_id,
                    route_option_id=option.route_option_id,
                    rank=option.rank,
                    data_scope=instance.data_scope,
                    preference_bias_dollars=preference_bias_dollars,
                    origin_airports=option.origin_airports,
                    destination_airports=option.destination_airports,
                    airlines=option.airlines,
                    day_offset=option.day_offset,
                    travel_date=travel_date,
                    start_time=option.start_time,
                    end_time=option.end_time,
                    fare_class_policy=option.fare_class_policy,
                    definition_signature=definition_signature,
                )
            )

    desired.sort(key=lambda item: (item.travel_date, item.rank, item.trip_instance_id))
    return desired
