from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

from googleapiclient.errors import HttpError

from app.models.base import utcnow
from app.services.booking_email_ingest import process_gmail_booking_message
from app.services.gmail_client import (
    GmailAuthorizationRequired,
    build_gmail_service,
    fetch_gmail_message,
    list_recent_inbox_message_ids,
)
from app.services.gmail_config import load_gmail_integration_config
from app.services.ids import new_id
from app.services.workflows import sync_and_persist
from app.settings import get_settings
from app.storage.repository import Repository


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("--max-messages must be >= 1")
    return parsed


def _emit_log(event: str, *, stream=sys.stdout, **fields: object) -> None:
    payload = {
        "timestamp": utcnow().isoformat(),
        "event": event,
        **fields,
    }
    print(json.dumps(payload, sort_keys=True, default=str), file=stream, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-messages", type=_positive_int, default=10)
    args = parser.parse_args()

    settings = get_settings()
    repository = Repository(settings)
    config = load_gmail_integration_config(settings)
    run_id = new_id("gmailpoll")
    stage = "config"
    processed_count = 0
    created_booking_count = 0
    created_unmatched_count = 0
    ignored_count = 0
    duplicate_count = 0
    error_count = 0

    try:
        if not config.enabled:
            _emit_log("run_disabled", run_id=run_id, pid=os.getpid(), reason="gmail_integration_disabled")
            return
        stage = "gmail_auth"
        service = build_gmail_service(settings)
        stage = "gmail_list"
        message_ids = list_recent_inbox_message_ids(
            service,
            label_ids=config.inbox_label_ids,
            max_results=min(args.max_messages, config.max_messages_per_poll),
        )
        _emit_log(
            "run_started",
            run_id=run_id,
            pid=os.getpid(),
            selected_message_count=len(message_ids),
            max_messages=args.max_messages,
        )
        stage = "process"
        any_state_changes = False
        for message_id in reversed(message_ids):
            message = fetch_gmail_message(service, message_id)
            with repository.transaction():
                result = process_gmail_booking_message(
                    repository,
                    message=message,
                    config=config,
                )
            processed_count += 1
            created_booking_count += len(result.created_bookings)
            created_unmatched_count += len(result.created_unmatched_bookings)
            status = str(result.event.processing_status)
            if status == "ignored":
                ignored_count += 1
            elif status == "duplicate":
                duplicate_count += 1
            elif status == "error":
                error_count += 1
            if result.created_bookings or result.created_unmatched_bookings:
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
                created_unmatched_booking_ids=result.event.result_unmatched_booking_ids,
                notes=result.event.notes,
            )

        if any_state_changes:
            stage = "sync"
            sync_and_persist(repository)
        _emit_log(
            "run_completed",
            run_id=run_id,
            pid=os.getpid(),
            processed_count=processed_count,
            created_booking_count=created_booking_count,
            created_unmatched_count=created_unmatched_count,
            ignored_count=ignored_count,
            duplicate_count=duplicate_count,
            error_count=error_count,
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

