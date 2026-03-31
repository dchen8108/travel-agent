from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.ingestion.google_flights_email_parser import parse_google_flights_email_bytes
from app.ingestion.observation_matcher import match_observations_to_trackers
from app.models.base import EmailParsedStatus
from app.models.email_event import EmailEvent
from app.services.ids import new_id
from app.storage.repository import Repository
from app.storage.uploaded_email_store import persist_uploaded_email


@dataclass
class ImportResult:
    email_event: EmailEvent
    matched_count: int
    ignored_count: int


def import_google_flights_email(
    repository: Repository,
    *,
    payload: bytes,
    filename: str,
) -> ImportResult:
    parsed = parse_google_flights_email_bytes(payload)
    existing_event = next(
        (
            event
            for event in repository.load_email_events()
            if parsed.message_id
            and event.source_message_id
            and event.source_message_id == parsed.message_id
        ),
        None,
    )
    if existing_event is not None:
        return ImportResult(
            email_event=existing_event,
            matched_count=existing_event.matched_observation_count,
            ignored_count=max(existing_event.observation_count - existing_event.matched_observation_count, 0),
        )
    email_event_id = new_id("email")
    saved_path = persist_uploaded_email(repository.settings.imported_email_dir, email_event_id, payload)

    trackers = repository.load_trackers()
    match_result = match_observations_to_trackers(parsed, trackers, email_event_id=email_event_id)

    parsed_status = EmailParsedStatus.PARSED
    if match_result.ignored_count:
        parsed_status = EmailParsedStatus.PARSED_WITH_IGNORED_OBSERVATIONS

    email_event = EmailEvent(
        email_event_id=email_event_id,
        source_message_id=parsed.message_id,
        received_at=parsed.received_at,
        subject=parsed.subject or filename,
        parsed_status=parsed_status,
        observation_count=len(parsed.observations),
        matched_observation_count=len(match_result.observations),
        imported_email_path=str(saved_path.relative_to(repository.settings.data_dir)),
        raw_excerpt=parsed.raw_excerpt,
    )

    email_events = repository.load_email_events()
    email_events.append(email_event)
    observations = repository.load_fare_observations()
    observations.extend(match_result.observations)
    repository.save_email_events(email_events)
    repository.save_fare_observations(observations)

    return ImportResult(
        email_event=email_event,
        matched_count=len(match_result.observations),
        ignored_count=match_result.ignored_count,
    )
