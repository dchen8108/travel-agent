from __future__ import annotations

from dataclasses import dataclass

from app.catalog import normalize_airline_code
from app.ingestion.google_flights_email_parser import ParsedGoogleFlightsEmail, ParsedGoogleFlightsObservation
from app.models.fare_observation import FareObservation
from app.models.tracker import Tracker
from app.route_options import arrival_time_from_time_line, departure_time_from_time_line, time_in_window
from app.services.ids import new_id


@dataclass
class MatchResult:
    observations: list[FareObservation]
    matched_tracker_ids: set[str]
    ignored_count: int


def _matching_trackers(
    parsed: ParsedGoogleFlightsObservation,
    trackers: list[Tracker],
) -> list[Tracker]:
    if parsed.is_nonstop is False or not parsed.origin_airport or not parsed.destination_airport:
        return []
    try:
        airline = normalize_airline_code(parsed.airline)
    except ValueError:
        return []
    departure_time = departure_time_from_time_line(parsed.time_line)

    matches: list[Tracker] = []
    for tracker in trackers:
        if tracker.travel_date != parsed.travel_date:
            continue
        if parsed.origin_airport not in tracker.origin_codes:
            continue
        if parsed.destination_airport not in tracker.destination_codes:
            continue
        if airline not in tracker.airline_codes:
            continue
        if not time_in_window(tracker.start_time, tracker.end_time, departure_time):
            continue
        matches.append(tracker)
    return matches


def match_observations_to_trackers(
    parsed_email: ParsedGoogleFlightsEmail,
    trackers: list[Tracker],
    *,
    email_event_id: str,
) -> MatchResult:
    observations: list[FareObservation] = []
    matched_tracker_ids: set[str] = set()
    ignored_count = 0

    for candidate in parsed_email.observations:
        matches = _matching_trackers(candidate, trackers)
        if len(matches) != 1:
            ignored_count += 1
            continue
        tracker = matches[0]
        matched_tracker_ids.add(tracker.tracker_id)
        observations.append(
            FareObservation(
                fare_observation_id=new_id("obs"),
                email_event_id=email_event_id,
                tracker_id=tracker.tracker_id,
                trip_instance_id=tracker.trip_instance_id,
                observed_at=parsed_email.received_at,
                airline=normalize_airline_code(candidate.airline),
                origin_airport=candidate.origin_airport,
                destination_airport=candidate.destination_airport,
                travel_date=candidate.travel_date,
                departure_time=departure_time_from_time_line(candidate.time_line) or tracker.start_time,
                arrival_time=arrival_time_from_time_line(candidate.time_line) or "",
                price=candidate.price,
                previous_price=candidate.previous_price,
                price_direction=candidate.price_direction or "",
                match_summary=f"{candidate.time_line} | {candidate.detail_line}",
            )
        )

    return MatchResult(
        observations=observations,
        matched_tracker_ids=matched_tracker_ids,
        ignored_count=ignored_count,
    )
