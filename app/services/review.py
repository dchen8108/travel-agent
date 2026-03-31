from __future__ import annotations

from collections import defaultdict

from app.models.base import EmailParsedStatus, ReviewStatus, SegmentType, TrackerStatus, utcnow
from app.models.email_event import EmailEvent
from app.models.fare_observation import FareObservation
from app.models.review_item import ReviewItem
from app.models.tracker import Tracker
from app.models.view_models import ReviewContext
from app.services.ids import new_id
from app.services.workflows import recompute_and_persist
from app.storage.repository import Repository


def build_review_contexts(
    email_events: list[EmailEvent],
    review_items: list[ReviewItem],
) -> list[ReviewContext]:
    items_by_event: dict[str, list[ReviewItem]] = {}
    for item in review_items:
        items_by_event.setdefault(item.email_event_id, []).append(item)

    contexts: list[ReviewContext] = []
    for event in sorted(email_events, key=lambda item: item.received_at, reverse=True):
        if event.email_event_id not in items_by_event:
            continue
        contexts.append(ReviewContext(event=event, items=items_by_event[event.email_event_id]))
    return contexts


def resolve_review_item(
    repository: Repository,
    review_item_id: str,
    tracker_id: str,
) -> ReviewItem:
    review_items = repository.load_review_items()
    trackers = repository.load_trackers()
    observations = repository.load_fare_observations()
    email_events = repository.load_email_events()

    review_item = next(item for item in review_items if item.review_item_id == review_item_id)
    tracker = next(item for item in trackers if item.tracker_id == tracker_id)
    event = next(item for item in email_events if item.email_event_id == review_item.email_event_id)

    observation = FareObservation(
        observation_id=new_id("obs"),
        tracker_id=tracker.tracker_id,
        trip_instance_id=tracker.trip_instance_id,
        segment_type=tracker.segment_type,
        source_id=event.source_message_id or event.email_event_id,
        observed_at=event.received_at,
        airline=review_item.observed_airline,
        price=review_item.observed_price or 0,
        outbound_summary=_segment_summary(review_item) if tracker.segment_type == SegmentType.OUTBOUND else "",
        return_summary=_segment_summary(review_item) if tracker.segment_type == SegmentType.RETURN else "",
        is_best_current_option=True,
    )
    observations.append(observation)
    review_item.status = ReviewStatus.RESOLVED
    review_item.resolved_tracker_id = tracker.tracker_id
    review_item.resolution_notes = "Matched manually in review queue."
    review_item.resolved_at = utcnow()

    tracker.tracking_status = TrackerStatus.SIGNAL_RECEIVED
    tracker.last_signal_at = event.received_at
    tracker.latest_observed_price = review_item.observed_price
    tracker.updated_at = utcnow()

    repository.save_fare_observations(observations)
    repository.save_review_items(review_items)
    repository.save_trackers(trackers)
    refresh_event_statuses(email_events, review_items)
    repository.save_email_events(email_events)
    recompute_and_persist(repository)
    return review_item


def ignore_review_item(repository: Repository, review_item_id: str) -> ReviewItem:
    review_items = repository.load_review_items()
    email_events = repository.load_email_events()
    review_item = next(item for item in review_items if item.review_item_id == review_item_id)
    review_item.status = ReviewStatus.IGNORED
    review_item.resolution_notes = "Ignored by user."
    review_item.resolved_at = utcnow()

    repository.save_review_items(review_items)
    refresh_event_statuses(email_events, review_items)
    repository.save_email_events(email_events)
    recompute_and_persist(repository)
    return review_item


def refresh_event_statuses(
    email_events: list[EmailEvent],
    review_items: list[ReviewItem],
) -> list[EmailEvent]:
    open_counts = defaultdict(int)
    for item in review_items:
        if item.status == ReviewStatus.OPEN:
            open_counts[item.email_event_id] += 1

    for event in email_events:
        event.parsed_status = (
            EmailParsedStatus.NEEDS_REVIEW
            if open_counts[event.email_event_id]
            else EmailParsedStatus.PARSED
        )
    return email_events


def candidate_trackers_for_review_item(
    review_item: ReviewItem,
    trackers: list[Tracker],
) -> list[Tracker]:
    matches: list[Tracker] = []
    for tracker in trackers:
        if review_item.observed_date and tracker.travel_date != review_item.observed_date:
            continue
        if review_item.observed_origin_airport and tracker.origin_airport != review_item.observed_origin_airport:
            continue
        if review_item.observed_destination_airport and tracker.destination_airport != review_item.observed_destination_airport:
            continue
        matches.append(tracker)
    return sorted(matches, key=lambda item: (item.travel_date, item.origin_airport, item.destination_airport))


def _segment_summary(review_item: ReviewItem) -> str:
    return " | ".join(
        part
        for part in (review_item.observed_time_line, review_item.observed_detail_line)
        if part
    )
