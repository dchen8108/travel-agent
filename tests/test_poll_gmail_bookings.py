from __future__ import annotations

from datetime import datetime

from googleapiclient.errors import HttpError
from httplib2 import Response

from app.jobs.poll_gmail_bookings import _select_message_ids_for_poll
from app.models.base import BookingEmailEventStatus
from app.models.booking_email_event import BookingEmailEvent


def _event(
    message_id: str,
    status: str,
    *,
    hour: int,
    extraction_attempt_count: int = 0,
    retryable: bool = True,
) -> BookingEmailEvent:
    return BookingEmailEvent(
        email_event_id=f"mail-{message_id}",
        gmail_message_id=message_id,
        gmail_thread_id=f"thread-{message_id}",
        gmail_history_id="12345",
        from_address="bookings@example.com",
        subject=f"Subject {message_id}",
        received_at=datetime(2026, 4, 1, hour, 0).astimezone(),
        processing_status=BookingEmailEventStatus(status),
        extraction_attempt_count=extraction_attempt_count,
        retryable=retryable,
    )


def test_select_message_ids_for_poll_backfills_unseen_and_retries_errors(repository, monkeypatch) -> None:
    repository.save_booking_email_events(
        [
            _event("msg-known", "resolved_auto", hour=9),
            _event("msg-retry", "error", hour=8),
        ]
    )

    monkeypatch.setattr(
        "app.jobs.poll_gmail_bookings.list_all_inbox_message_ids",
        lambda service, *, label_ids: ["msg-new", "msg-retry", "msg-known"],
    )
    monkeypatch.setattr(
        "app.jobs.poll_gmail_bookings.get_mailbox_profile",
        lambda service: {"email_address": "booking@example.com", "history_id": "200"},
    )

    selection = _select_message_ids_for_poll(
        repository,
        object(),
        inbox_label_ids=["INBOX"],
        sync_state_last_history_id="",
        max_messages=5,
        retry_limit=5,
        max_retry_attempts=2,
    )

    assert selection.message_ids == ["msg-new", "msg-retry"]
    assert selection.latest_history_id == "200"
    assert selection.source_mode == "backfill"


def test_select_message_ids_for_poll_uses_incremental_history(repository, monkeypatch) -> None:
    repository.save_booking_email_events(
        [
            _event("msg-known", "resolved_auto", hour=9),
            _event("msg-retry", "error", hour=8),
        ]
    )

    monkeypatch.setattr(
        "app.jobs.poll_gmail_bookings.list_message_ids_since_history",
        lambda service, *, start_history_id, label_id=None: (["msg-fresh", "msg-known"], "300"),
    )

    selection = _select_message_ids_for_poll(
        repository,
        object(),
        inbox_label_ids=["INBOX"],
        sync_state_last_history_id="250",
        max_messages=5,
        retry_limit=5,
        max_retry_attempts=2,
    )

    assert selection.message_ids == ["msg-fresh", "msg-retry"]
    assert selection.latest_history_id == "300"
    assert selection.source_mode == "incremental"


def test_select_message_ids_for_poll_falls_back_to_backfill_on_expired_history(repository, monkeypatch) -> None:
    repository.save_booking_email_events([_event("msg-known", "resolved_auto", hour=9)])

    def raise_history_error(service, *, start_history_id, label_id=None):
        raise HttpError(Response({"status": "404"}), b'{"error":{"message":"startHistoryId invalid"}}')

    monkeypatch.setattr(
        "app.jobs.poll_gmail_bookings.list_message_ids_since_history",
        raise_history_error,
    )
    monkeypatch.setattr(
        "app.jobs.poll_gmail_bookings.list_all_inbox_message_ids",
        lambda service, *, label_ids: ["msg-backfill", "msg-known"],
    )
    monkeypatch.setattr(
        "app.jobs.poll_gmail_bookings.get_mailbox_profile",
        lambda service: {"email_address": "booking@example.com", "history_id": "400"},
    )

    selection = _select_message_ids_for_poll(
        repository,
        object(),
        inbox_label_ids=["INBOX"],
        sync_state_last_history_id="350",
        max_messages=5,
        retry_limit=5,
        max_retry_attempts=2,
    )

    assert selection.message_ids == ["msg-backfill"]
    assert selection.latest_history_id == "400"
    assert selection.source_mode == "history_reset_backfill"


def test_select_message_ids_for_poll_skips_nonretryable_and_exhausted_errors(repository, monkeypatch) -> None:
    repository.save_booking_email_events(
        [
            _event("msg-transient", "error", hour=8, extraction_attempt_count=1, retryable=True),
            _event("msg-terminal", "error", hour=7, extraction_attempt_count=1, retryable=False),
            _event("msg-exhausted", "error", hour=6, extraction_attempt_count=2, retryable=True),
        ]
    )

    monkeypatch.setattr(
        "app.jobs.poll_gmail_bookings.list_all_inbox_message_ids",
        lambda service, *, label_ids: [],
    )
    monkeypatch.setattr(
        "app.jobs.poll_gmail_bookings.get_mailbox_profile",
        lambda service: {"email_address": "booking@example.com", "history_id": "200"},
    )

    selection = _select_message_ids_for_poll(
        repository,
        object(),
        inbox_label_ids=["INBOX"],
        sync_state_last_history_id="",
        max_messages=5,
        retry_limit=5,
        max_retry_attempts=2,
    )

    assert selection.message_ids == ["msg-transient"]
    assert selection.latest_history_id == "200"
    assert selection.source_mode == "backfill"


def test_select_message_ids_for_poll_applies_hard_cap_after_deduping(repository, monkeypatch) -> None:
    repository.save_booking_email_events(
        [
            _event("msg-retry", "error", hour=8),
        ]
    )

    monkeypatch.setattr(
        "app.jobs.poll_gmail_bookings.list_all_inbox_message_ids",
        lambda service, *, label_ids: ["msg-new-1", "msg-new-2", "msg-new-3"],
    )
    monkeypatch.setattr(
        "app.jobs.poll_gmail_bookings.get_mailbox_profile",
        lambda service: {"email_address": "booking@example.com", "history_id": "200"},
    )

    selection = _select_message_ids_for_poll(
        repository,
        object(),
        inbox_label_ids=["INBOX"],
        sync_state_last_history_id="",
        max_messages=2,
        retry_limit=2,
        max_retry_attempts=2,
    )

    assert selection.message_ids == ["msg-new-1", "msg-new-2"]
    assert selection.new_message_ids == ["msg-new-1", "msg-new-2", "msg-new-3"]
    assert selection.retry_message_ids == ["msg-retry"]
