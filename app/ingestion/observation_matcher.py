from __future__ import annotations

from dataclasses import dataclass

from app.ingestion.google_flights_email_parser import ParsedGoogleFlightsEmail, ParsedGoogleFlightsObservation
from app.models.base import SegmentType
from app.models.fare_observation import FareObservation
from app.models.review_item import ReviewItem
from app.models.tracker import Tracker
from app.services.ids import new_id


@dataclass
class MatchResult:
    observations: list[FareObservation]
    review_items: list[ReviewItem]
    matched_tracker_ids: set[str]


def _matching_trackers(
    parsed: ParsedGoogleFlightsObservation,
    trackers: list[Tracker],
) -> list[Tracker]:
    matches: list[Tracker] = []
    if not parsed.origin_airport or not parsed.destination_airport:
        return matches
    for tracker in trackers:
        if tracker.travel_date != parsed.travel_date:
            continue
        if tracker.origin_airport != parsed.origin_airport:
            continue
        if tracker.destination_airport != parsed.destination_airport:
            continue
        matches.append(tracker)
    return matches


def match_observations_to_trackers(
    parsed_email: ParsedGoogleFlightsEmail,
    trackers: list[Tracker],
) -> MatchResult:
    observations: list[FareObservation] = []
    review_items: list[ReviewItem] = []
    matched_tracker_ids: set[str] = set()

    for candidate in parsed_email.observations:
        matches = _matching_trackers(candidate, trackers)
        if len(matches) == 1:
            tracker = matches[0]
            matched_tracker_ids.add(tracker.tracker_id)
            observations.append(
                FareObservation(
                    observation_id=new_id("obs"),
                    tracker_id=tracker.tracker_id,
                    trip_instance_id=tracker.trip_instance_id,
                    segment_type=tracker.segment_type,
                    source_id=parsed_email.message_id or parsed_email.subject,
                    observed_at=parsed_email.received_at,
                    airline=candidate.airline,
                    price=candidate.price,
                    outbound_summary=f"{candidate.time_line} | {candidate.detail_line}"
                    if tracker.segment_type == SegmentType.OUTBOUND
                    else "",
                    return_summary=f"{candidate.time_line} | {candidate.detail_line}"
                    if tracker.segment_type == SegmentType.RETURN
                    else "",
                )
            )
        else:
            review_items.append(
                ReviewItem(
                    review_item_id=new_id("rev"),
                    email_event_id="",
                    observed_route=candidate.route_text,
                    observed_date=candidate.travel_date,
                    observed_origin_airport=candidate.origin_airport or "",
                    observed_destination_airport=candidate.destination_airport or "",
                    observed_airline=candidate.airline,
                    observed_price=candidate.price,
                    observed_previous_price=candidate.previous_price,
                    observed_price_direction=candidate.price_direction or "",
                    observed_time_line=candidate.time_line,
                    observed_detail_line=candidate.detail_line,
                    observed_flight_url=candidate.flight_url,
                    candidate_tracker_ids="|".join(
                        tracker.tracker_id for tracker in matches
                    ),
                )
            )

    return MatchResult(
        observations=observations,
        review_items=review_items,
        matched_tracker_ids=matched_tracker_ids,
    )
