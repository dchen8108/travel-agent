from __future__ import annotations

from dataclasses import dataclass

from app.ingestion.google_flights_email_parser import ParsedGoogleFlightsEmail, ParsedGoogleFlightsObservation
from app.models.base import SegmentType
from app.models.fare_observation import FareObservation
from app.models.review_item import ReviewItem
from app.models.tracker import Tracker
from app.route_details import RankedRouteDetail, route_detail_matches_time_line
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

    airline_filtered = [
        tracker
        for tracker in matches
        if not tracker.detail_airline or not parsed.airline or tracker.detail_airline == parsed.airline
    ]
    candidate_matches = airline_filtered or matches

    nonstop_filtered = [
        tracker
        for tracker in candidate_matches
        if not tracker.detail_nonstop_only or parsed.is_nonstop is not False
    ]
    if parsed.is_nonstop is False:
        candidate_matches = nonstop_filtered
    else:
        candidate_matches = nonstop_filtered or candidate_matches
    if len(candidate_matches) <= 1:
        return candidate_matches

    time_filtered: list[Tracker] = []
    for tracker in candidate_matches:
        detail = RankedRouteDetail(
            origin_airport=tracker.origin_airport,
            destination_airport=tracker.destination_airport,
            weekday=tracker.detail_weekday or tracker.travel_date.strftime("%A"),
            start_time=tracker.detail_time_start or "00:00",
            end_time=tracker.detail_time_end or "23:59",
            airline=tracker.detail_airline,
            nonstop_only=tracker.detail_nonstop_only,
        )
        if route_detail_matches_time_line(detail, parsed.time_line):
            time_filtered.append(tracker)
    if len(time_filtered) == 1:
        return time_filtered
    return time_filtered or candidate_matches


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
