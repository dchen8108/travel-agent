from __future__ import annotations

import argparse
from dataclasses import dataclass
from email.utils import parseaddr
import json
import os
import sys
import traceback

from googleapiclient.errors import HttpError

from app.jobs.cli_types import positive_int_argument
from app.models.base import BookingEmailEventStatus
from app.models.base import utcnow
from app.models.booking_email_event import BookingEmailEvent
from app.services.booking_email_ingest import loggable_debug_fields, process_gmail_booking_message
from app.services.gmail_client import (
    GmailAuthorizationRequired,
    GmailMessage,
    build_gmail_service,
    fetch_gmail_message,
    get_mailbox_profile,
    list_all_inbox_message_ids,
    list_message_ids_since_history,
)
from app.services.gmail_config import load_gmail_integration_config
from app.services.gmail_sync_state import load_gmail_sync_state, save_gmail_sync_state
from app.services.ids import new_id
from app.services.workflows import sync_and_persist
from app.settings import get_settings
from app.storage.repository import Repository


def _http_error_status(exc: HttpError) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status
    return getattr(getattr(exc, "resp", None), "status", None)


def _emit_log(event: str, *, stream=sys.stdout, **fields: object) -> None:
    payload = {
        "timestamp": utcnow().isoformat(),
        "event": event,
        **fields,
    }
    print(json.dumps(payload, sort_keys=True, default=str), file=stream, flush=True)


def _dedupe_message_ids(message_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for message_id in message_ids:
        if not message_id or message_id in seen:
            continue
        seen.add(message_id)
        ordered.append(message_id)
    return ordered


def _retry_message_ids(repository: Repository, *, limit: int, max_retry_attempts: int) -> list[str]:
    errored_events = repository.load_retryable_booking_email_events(
        max_retry_attempts=max_retry_attempts,
        limit=limit,
    )
    return [event.gmail_message_id for event in errored_events]


def _normalized_from_address(value: str) -> str:
    _name, address = parseaddr(value)
    return (address or value).strip().lower()


def _sender_query(allowed_from_addresses: list[str]) -> str:
    normalized = [_normalized_from_address(value) for value in allowed_from_addresses if value.strip()]
    if not normalized:
        return ""
    if len(normalized) == 1:
        return f"from:{normalized[0]}"
    return "(" + " OR ".join(f"from:{address}" for address in normalized) + ")"


@dataclass
class MessageSelection:
    message_ids: list[str]
    latest_history_id: str
    source_mode: str
    new_message_ids: list[str]
    retry_message_ids: list[str]
    history_id_before: str


def _history_id_after_run(
    *,
    history_id_before: str,
    latest_history_id: str,
    retryable_error_found: bool,
) -> str:
    if retryable_error_found and history_id_before:
        return history_id_before
    return latest_history_id


def _retryable_message_error(exc: Exception) -> bool:
    if isinstance(exc, HttpError):
        status = _http_error_status(exc)
        return status in {408, 409, 425, 429, 500, 502, 503, 504}
    return False


def _find_existing_event(repository: Repository, gmail_message_id: str) -> BookingEmailEvent | None:
    return repository.get_booking_email_event_by_message_id(gmail_message_id)


def _record_message_processing_error(
    repository: Repository,
    *,
    message_id: str,
    history_id: str = "",
    error: Exception,
    error_stage: str,
    message: GmailMessage | None = None,
) -> BookingEmailEvent:
    event = _find_existing_event(repository, message_id) or BookingEmailEvent(
        email_event_id=new_id("mail"),
        gmail_message_id=message_id,
    )
    if message is not None:
        event.gmail_thread_id = message.gmail_thread_id
        event.gmail_history_id = message.gmail_history_id
        event.from_address = message.from_address
        event.subject = message.subject
        event.received_at = message.received_at
    elif history_id:
        event.gmail_history_id = history_id
    event.processing_status = BookingEmailEventStatus.ERROR
    event.email_kind = "unknown"
    event.extraction_attempt_count += 1
    event.retryable = _retryable_message_error(error)
    event.notes = f"{error_stage} failed: {type(error).__name__}: {error}"
    if not event.retryable:
        event.notes = f"{event.notes} This email will not be retried automatically."
    event.updated_at = utcnow()
    repository.upsert_booking_email_event(event)
    return event


def _select_message_ids_for_poll(
    repository: Repository,
    service,
    *,
    inbox_label_ids: list[str],
    allowed_from_addresses: list[str] | None = None,
    sync_state_last_history_id: str,
    max_messages: int,
    retry_limit: int,
    max_retry_attempts: int,
) -> MessageSelection:
    existing_message_ids = repository.load_booking_email_message_ids()
    retry_ids = _retry_message_ids(repository, limit=retry_limit, max_retry_attempts=max_retry_attempts)
    sender_query = _sender_query(allowed_from_addresses or [])

    if sync_state_last_history_id:
        latest_history_id = sync_state_last_history_id
        try:
            incremental_ids, latest_history_id = list_message_ids_since_history(
                service,
                start_history_id=sync_state_last_history_id,
                label_id=inbox_label_ids[0] if len(inbox_label_ids) == 1 else None,
            )
            source_mode = "incremental"
        except HttpError as exc:
            if _http_error_status(exc) == 404 or "startHistoryId" in str(exc):
                if sender_query:
                    incremental_ids = list_all_inbox_message_ids(
                        service,
                        label_ids=inbox_label_ids,
                        query=sender_query,
                    )
                else:
                    incremental_ids = list_all_inbox_message_ids(service, label_ids=inbox_label_ids)
                latest_history_id = get_mailbox_profile(service)["history_id"]
                source_mode = "history_reset_backfill"
            else:
                raise
        new_ids = [message_id for message_id in incremental_ids if message_id not in existing_message_ids]
        return MessageSelection(
            message_ids=_dedupe_message_ids(new_ids + retry_ids)[:max_messages],
            latest_history_id=latest_history_id,
            source_mode=source_mode,
            new_message_ids=new_ids,
            retry_message_ids=retry_ids,
            history_id_before=sync_state_last_history_id,
        )

    mailbox_profile = get_mailbox_profile(service)
    if sender_query:
        backfill_ids = list_all_inbox_message_ids(service, label_ids=inbox_label_ids, query=sender_query)
    else:
        backfill_ids = list_all_inbox_message_ids(service, label_ids=inbox_label_ids)
    new_ids = [message_id for message_id in backfill_ids if message_id not in existing_message_ids]
    return MessageSelection(
        message_ids=_dedupe_message_ids(new_ids + retry_ids)[:max_messages],
        latest_history_id=mailbox_profile["history_id"],
        source_mode="backfill",
        new_message_ids=new_ids,
        retry_message_ids=retry_ids,
        history_id_before="",
    )


def main() -> None:
    settings = get_settings()
    config = load_gmail_integration_config(settings)
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-messages", type=positive_int_argument("--max-messages"), default=config.launchd_max_messages)
    args = parser.parse_args()

    repository = Repository(settings)
    run_id = new_id("gmailpoll")
    stage = "config"
    processed_count = 0
    created_booking_count = 0
    created_unlinked_count = 0
    ignored_count = 0
    duplicate_count = 0
    error_count = 0

    try:
        if not config.enabled:
            _emit_log("run_disabled", run_id=run_id, pid=os.getpid(), reason="gmail_integration_disabled")
            return
        stage = "gmail_auth"
        service = build_gmail_service(settings)
        sync_state = load_gmail_sync_state(settings)
        stage = "gmail_list"
        effective_max_messages = min(args.max_messages, config.max_messages_per_poll)
        selection = _select_message_ids_for_poll(
            repository,
            service,
            inbox_label_ids=config.inbox_label_ids,
            allowed_from_addresses=config.allowed_from_addresses,
            sync_state_last_history_id=sync_state.last_history_id,
            max_messages=effective_max_messages,
            retry_limit=effective_max_messages,
            max_retry_attempts=config.max_retry_attempts,
        )
        _emit_log(
            "run_started",
            run_id=run_id,
            pid=os.getpid(),
            selected_message_count=len(selection.message_ids),
            selected_message_ids=selection.message_ids,
            new_message_count=len(selection.new_message_ids),
            new_message_ids=selection.new_message_ids,
            retry_message_count=len(selection.retry_message_ids),
            retry_message_ids=selection.retry_message_ids,
            effective_max_messages=effective_max_messages,
            max_messages=args.max_messages,
            history_mode=selection.source_mode,
            history_id_before=selection.history_id_before,
        )
        stage = "process"
        any_state_changes = False
        retryable_error_message_ids: list[str] = []
        for message_id in reversed(selection.message_ids):
            try:
                message = fetch_gmail_message(service, message_id)
            except HttpError as exc:
                with repository.transaction():
                    event = _record_message_processing_error(
                        repository,
                        message_id=message_id,
                        error=exc,
                        error_stage="gmail_fetch",
                    )
                processed_count += 1
                error_count += 1
                if event.retryable:
                    retryable_error_message_ids.append(message_id)
                _emit_log(
                    "message_processed",
                    run_id=run_id,
                    gmail_message_id=message_id,
                    subject=event.subject,
                    from_address=event.from_address,
                    processing_status=str(event.processing_status),
                    email_kind=event.email_kind,
                    extraction_confidence=event.extraction_confidence,
                    created_booking_ids=event.result_booking_ids,
                    created_unlinked_booking_ids=event.result_unmatched_booking_ids,
                    notes=event.notes,
                    debug={"error_stage": "gmail_fetch", "retryable": event.retryable},
                )
                continue

            with repository.transaction():
                result = process_gmail_booking_message(
                    repository,
                    message=message,
                    config=config,
                )

            processed_count += 1
            created_booking_count += len(result.created_bookings)
            created_unlinked_count += len(result.created_unlinked_bookings)
            status = str(result.event.processing_status)
            if status == "ignored":
                ignored_count += 1
            elif status == "duplicate":
                duplicate_count += 1
            elif status == "error":
                error_count += 1
                if result.event.retryable:
                    retryable_error_message_ids.append(result.event.gmail_message_id)
            if result.state_changed:
                any_state_changes = True
            _emit_log(
                "message_processed",
                run_id=run_id,
                gmail_message_id=result.event.gmail_message_id,
                subject=result.event.subject,
                from_address=result.event.from_address,
                processing_status=status,
                email_kind=result.event.email_kind,
                extraction_confidence=result.event.extraction_confidence,
                created_booking_ids=result.event.result_booking_ids,
                created_unlinked_booking_ids=result.event.result_unmatched_booking_ids,
                notes=result.event.notes,
                debug=loggable_debug_fields(
                    result.debug_fields,
                    include_model_io=config.debug_log_model_io,
                ),
            )

        if any_state_changes:
            stage = "sync"
            sync_and_persist(repository)
        history_id_after = _history_id_after_run(
            history_id_before=selection.history_id_before,
            latest_history_id=selection.latest_history_id,
            retryable_error_found=bool(retryable_error_message_ids),
        )
        sync_state.last_history_id = history_id_after
        sync_state.last_polled_at = utcnow()
        save_gmail_sync_state(settings, sync_state)
        _emit_log(
            "run_completed",
            run_id=run_id,
            pid=os.getpid(),
            processed_count=processed_count,
            created_booking_count=created_booking_count,
            created_unlinked_count=created_unlinked_count,
            ignored_count=ignored_count,
            duplicate_count=duplicate_count,
            error_count=error_count,
            history_id_after=history_id_after,
            history_advanced=history_id_after == selection.latest_history_id,
            retryable_error_message_ids=retryable_error_message_ids,
            state_changed=any_state_changes,
        )
    except (GmailAuthorizationRequired, HttpError, RuntimeError, ValueError) as exc:
        _emit_log(
            "run_failed",
            stream=sys.stderr,
            run_id=run_id,
            pid=os.getpid(),
            stage=stage,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise
    except Exception as exc:
        _emit_log(
            "run_failed",
            stream=sys.stderr,
            run_id=run_id,
            pid=os.getpid(),
            stage=stage,
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        raise


if __name__ == "__main__":
    main()
