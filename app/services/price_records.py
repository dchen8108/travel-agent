from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models.price_record import PriceRecord
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.services.google_flights_fetcher import GoogleFlightsOffer
from app.services.ids import new_id


@dataclass(frozen=True)
class SuccessfulFetchRecord:
    fetch_target_id: str
    fetched_at: datetime
    offers: list[GoogleFlightsOffer]


def build_price_records(
    *,
    trips: list[Trip],
    trip_instances: list[TripInstance],
    trackers: list[Tracker],
    fetch_targets: list[TrackerFetchTarget],
    successful_fetches: list[SuccessfulFetchRecord],
) -> list[PriceRecord]:
    trips_by_id = {trip.trip_id: trip for trip in trips}
    instances_by_id = {instance.trip_instance_id: instance for instance in trip_instances}
    trackers_by_id = {tracker.tracker_id: tracker for tracker in trackers}
    targets_by_id = {target.fetch_target_id: target for target in fetch_targets}

    records: list[PriceRecord] = []
    for fetch in successful_fetches:
        target = targets_by_id.get(fetch.fetch_target_id)
        if target is None:
            continue
        tracker = trackers_by_id.get(target.tracker_id)
        if tracker is None:
            continue
        trip_instance = instances_by_id.get(target.trip_instance_id)
        if trip_instance is None:
            continue
        trip = trips_by_id.get(trip_instance.trip_id)
        fetch_event_id = new_id("fetch")
        ordered_offers = sorted(
            fetch.offers,
            key=lambda item: (item.price, item.airline, item.departure_label, item.arrival_label),
        )
        for index, offer in enumerate(ordered_offers, start=1):
            records.append(
                PriceRecord(
                    price_record_id=new_id("price"),
                    fetch_event_id=fetch_event_id,
                    observed_at=fetch.fetched_at,
                    data_scope=tracker.data_scope,
                    fetch_target_id=target.fetch_target_id,
                    tracker_id=tracker.tracker_id,
                    trip_instance_id=trip_instance.trip_instance_id,
                    trip_id=trip_instance.trip_id,
                    route_option_id=tracker.route_option_id,
                    tracker_definition_signature=tracker.definition_signature,
                    tracker_rank=tracker.rank,
                    search_origin_airports=tracker.origin_airports,
                    search_destination_airports=tracker.destination_airports,
                    search_airlines=tracker.airlines,
                    search_day_offset=tracker.day_offset,
                    search_travel_date=tracker.travel_date,
                    search_start_time=tracker.start_time,
                    search_end_time=tracker.end_time,
                    search_fare_class=tracker.fare_class,
                    query_origin_airport=target.origin_airport,
                    query_destination_airport=target.destination_airport,
                    airline=offer.airline,
                    departure_label=offer.departure_label,
                    arrival_label=offer.arrival_label,
                    price=offer.price,
                    offer_rank=index,
                )
            )
    return records
