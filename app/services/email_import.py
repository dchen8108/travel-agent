from __future__ import annotations

from app.ingestion.google_flights_email_parser import parse_google_flights_email_bytes
from app.ingestion.observation_matcher import match_observations_to_trackers
from app.models.base import EmailParsedStatus
from app.models.email_event import EmailEvent
from app.services.ids import new_id
from app.services.workflows import recompute_and_persist, refresh_tracker_projections
from app.storage.repository import Repository
from app.storage.uploaded_email_store import persist_uploaded_email


def import_email_payload(repository: Repository, filename: str, payload: bytes) -> EmailEvent:
    repository.ensure_data_dir()
    parsed_email = parse_google_flights_email_bytes(payload)
    events = repository.load_email_events()
    if parsed_email.message_id:
        existing = next(
            (
                event
                for event in events
                if event.source_message_id == parsed_email.message_id
            ),
            None,
        )
        if existing is not None:
            return existing

    email_event_id = new_id("mail")
    stored_path = persist_uploaded_email(repository.settings.imported_email_dir, email_event_id, payload)
    trackers = repository.load_trackers()
    observations = repository.load_fare_observations()
    review_items = repository.load_review_items()

    match_result = match_observations_to_trackers(parsed_email, trackers)
    parsed_status = (
        EmailParsedStatus.PARSED
        if match_result.observations and not match_result.review_items
        else EmailParsedStatus.NEEDS_REVIEW
        if match_result.review_items
        else EmailParsedStatus.UNMATCHED
    )

    event = EmailEvent(
        email_event_id=email_event_id,
        source_message_id=parsed_email.message_id,
        received_at=parsed_email.received_at,
        subject=parsed_email.subject or filename,
        parsed_status=parsed_status,
        observation_count=len(parsed_email.observations),
        imported_email_path=str(stored_path.relative_to(repository.settings.data_dir)),
        raw_excerpt=parsed_email.plain_text[:1200].strip(),
    )
    events.append(event)

    for review_item in match_result.review_items:
        review_item.email_event_id = event.email_event_id
    review_items.extend(match_result.review_items)
    observations.extend(match_result.observations)
    refresh_tracker_projections(trackers, observations)

    repository.save_email_events(events)
    repository.save_review_items(review_items)
    repository.save_fare_observations(observations)
    repository.save_trackers(trackers)
    recompute_and_persist(repository)
    return event
