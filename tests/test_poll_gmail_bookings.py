from __future__ import annotations

from datetime import datetime

from googleapiclient.errors import HttpError
from httplib2 import Response

from app.jobs.poll_gmail_bookings import (
    _history_id_after_run,
    _process_message_with_extraction_retries,
    _rate_limited_extraction_retry_delay_seconds,
    _record_message_processing_error,
    _select_message_ids_for_poll,
)
from app.models.base import BookingEmailEventStatus
from app.models.booking_email_event import BookingEmailEvent
from app.models.gmail_integration import GmailIntegrationConfig
from app.services.booking_email_ingest import BookingEmailProcessResult
from app.services.gmail_client import GmailMessage


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
    repository.append_booking_email_events(
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
    repository.append_booking_email_events(
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


def test_select_message_ids_for_poll_uses_sender_query_for_backfill(repository, monkeypatch) -> None:
    seen_queries: list[str] = []

    def list_all(service, *, label_ids, query=""):
        seen_queries.append(query)
        return ["msg-new"]

    monkeypatch.setattr(
        "app.jobs.poll_gmail_bookings.list_all_inbox_message_ids",
        list_all,
    )
    monkeypatch.setattr(
        "app.jobs.poll_gmail_bookings.get_mailbox_profile",
        lambda service: {"email_address": "booking@example.com", "history_id": "200"},
    )

    selection = _select_message_ids_for_poll(
        repository,
        object(),
        inbox_label_ids=["INBOX"],
        allowed_from_addresses=["Forwarder <forwarder@example.com>"],
        sync_state_last_history_id="",
        max_messages=5,
        retry_limit=5,
        max_retry_attempts=2,
    )

    assert selection.message_ids == ["msg-new"]
    assert seen_queries == ["from:forwarder@example.com"]


def test_select_message_ids_for_poll_falls_back_to_backfill_on_expired_history(repository, monkeypatch) -> None:
    repository.append_booking_email_events([_event("msg-known", "resolved_auto", hour=9)])

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


def test_select_message_ids_for_poll_falls_back_to_backfill_on_http_error_status(repository, monkeypatch) -> None:
    repository.append_booking_email_events([_event("msg-known", "resolved_auto", hour=9)])

    class _RespOnlyHttpError(HttpError):
        @property
        def status_code(self):
            return None

    error = _RespOnlyHttpError(Response({"status": "404"}), b'{"error":{"message":"History expired"}}')

    def raise_history_error(service, *, start_history_id, label_id=None):
        raise error

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
        lambda service: {"email_address": "booking@example.com", "history_id": "401"},
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
    assert selection.latest_history_id == "401"
    assert selection.source_mode == "history_reset_backfill"


def test_select_message_ids_for_poll_skips_nonretryable_and_exhausted_errors(repository, monkeypatch) -> None:
    repository.append_booking_email_events(
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


def test_select_message_ids_for_poll_keeps_rate_limited_errors_retryable_longer(repository, monkeypatch) -> None:
    rate_limited = _event("msg-rate-limited", "error", hour=8, extraction_attempt_count=2, retryable=True)
    rate_limited.notes = "Extraction failed: BookingExtractionError: Error code: 429 rate_limit_exceeded."
    repository.append_booking_email_events(
        [
            rate_limited,
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

    assert selection.message_ids == ["msg-rate-limited"]


def test_select_message_ids_for_poll_applies_hard_cap_after_deduping(repository, monkeypatch) -> None:
    repository.append_booking_email_events(
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
    assert selection.truncated is True


def test_record_message_processing_error_reuses_existing_event_and_marks_terminal_404(repository) -> None:
    existing = _event("msg-known", "error", hour=8, extraction_attempt_count=1, retryable=True)
    repository.append_booking_email_events([existing])

    error = HttpError(Response({"status": "404"}), b'{"error":{"message":"Not Found"}}')
    updated = _record_message_processing_error(
        repository,
        message_id="msg-known",
        history_id="999",
        error=error,
        error_stage="gmail_fetch",
    )

    assert updated.email_event_id == existing.email_event_id
    assert updated.processing_status == BookingEmailEventStatus.ERROR
    assert updated.retryable is False
    assert updated.extraction_attempt_count == 2
    assert "This email will not be retried automatically." in updated.notes


def test_rate_limited_extraction_retry_delay_parses_openai_retry_after() -> None:
    event = _event("msg-rate-limit", "error", hour=8, extraction_attempt_count=1, retryable=True)
    event.notes = (
        "Extraction failed: BookingExtractionError: Error code: 429 - "
        "rate_limit_exceeded. Please try again in 3.39s."
    )

    retry_delay = _rate_limited_extraction_retry_delay_seconds(event, max_retry_attempts=2)

    assert retry_delay is not None
    assert 3.5 < retry_delay < 4.0


def test_process_message_retries_rate_limited_extraction_in_same_run(repository, monkeypatch) -> None:
    message = GmailMessage(
        gmail_message_id="msg-rate-limit",
        gmail_thread_id="thread-msg-rate-limit",
        gmail_history_id="12345",
        from_address="bookings@example.com",
        subject="Booking confirmation",
        received_at=datetime(2026, 4, 1, 12, 0).astimezone(),
        body_text="Confirmation code ABC123",
    )
    calls = 0

    def fake_process(repository, *, message, config):
        nonlocal calls
        calls += 1
        if calls == 1:
            event = _event(message.gmail_message_id, "error", hour=8, extraction_attempt_count=1, retryable=True)
            event.notes = "Extraction failed: BookingExtractionError: Error code: 429. Please try again in 0.1s."
            return BookingEmailProcessResult(event=event, created_bookings=[], created_unlinked_bookings=[])
        event = _event(message.gmail_message_id, "resolved_auto", hour=8, extraction_attempt_count=2)
        event.result_booking_ids = "book_123"
        return BookingEmailProcessResult(event=event, created_bookings=[], created_unlinked_bookings=[])

    sleep_delays: list[float] = []
    monkeypatch.setattr("app.jobs.poll_gmail_bookings.process_gmail_booking_message", fake_process)

    result = _process_message_with_extraction_retries(
        repository,
        message=message,
        config=GmailIntegrationConfig(max_retry_attempts=2),
        run_id="run_test",
        sleep_func=sleep_delays.append,
    )

    assert calls == 2
    assert sleep_delays == [1.0]
    assert result.event.processing_status == BookingEmailEventStatus.RESOLVED_AUTO


def test_history_id_after_run_preserves_incremental_checkpoint_when_retryable_errors_occur() -> None:
    assert _history_id_after_run(
        history_id_before="250",
        latest_history_id="300",
        retryable_error_found=True,
    ) == "250"


def test_history_id_after_run_advances_when_no_retryable_errors_occur() -> None:
    assert _history_id_after_run(
        history_id_before="250",
        latest_history_id="300",
        retryable_error_found=False,
    ) == "300"


def test_history_id_after_run_advances_initial_backfill_even_when_retryable_errors_occur() -> None:
    assert _history_id_after_run(
        history_id_before="",
        latest_history_id="300",
        retryable_error_found=True,
    ) == "300"


def test_history_id_after_run_preserves_checkpoint_when_selection_is_truncated() -> None:
    assert _history_id_after_run(
        history_id_before="250",
        latest_history_id="300",
        retryable_error_found=False,
        selection_truncated=True,
    ) == "250"


def test_history_id_after_run_repeats_initial_backfill_when_selection_is_truncated() -> None:
    assert _history_id_after_run(
        history_id_before="",
        latest_history_id="300",
        retryable_error_found=False,
        selection_truncated=True,
    ) == ""
