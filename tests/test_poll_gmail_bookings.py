from __future__ import annotations

from datetime import datetime

from googleapiclient.errors import HttpError
from httplib2 import Response

from app.jobs.poll_gmail_bookings import _select_message_ids_for_poll
from app.models.base import BookingEmailEventStatus
from app.models.booking_email_event import BookingEmailEvent


def _event(message_id: str, status: str, *, hour: int) -> BookingEmailEvent:
    return BookingEmailEvent(
        email_event_id=f"mail-{message_id}",
        gmail_message_id=message_id,
        gmail_thread_id=f"thread-{message_id}",
        gmail_history_id="12345",
        from_address="bookings@example.com",
        subject=f"Subject {message_id}",
        received_at=datetime(2026, 4, 1, hour, 0).astimezone(),
        processing_status=BookingEmailEventStatus(status),
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

    message_ids, latest_history_id, mode = _select_message_ids_for_poll(
        repository,
        object(),
        inbox_label_ids=["INBOX"],
        sync_state_last_history_id="",
        retry_limit=5,
    )

    assert message_ids == ["msg-new", "msg-retry"]
    assert latest_history_id == "200"
    assert mode == "backfill"


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

    message_ids, latest_history_id, mode = _select_message_ids_for_poll(
        repository,
        object(),
        inbox_label_ids=["INBOX"],
        sync_state_last_history_id="250",
        retry_limit=5,
    )

    assert message_ids == ["msg-fresh", "msg-retry"]
    assert latest_history_id == "300"
    assert mode == "incremental"


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

    message_ids, latest_history_id, mode = _select_message_ids_for_poll(
        repository,
        object(),
        inbox_label_ids=["INBOX"],
        sync_state_last_history_id="350",
        retry_limit=5,
    )

    assert message_ids == ["msg-backfill"]
    assert latest_history_id == "400"
    assert mode == "history_reset_backfill"
