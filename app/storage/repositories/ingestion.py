from __future__ import annotations

from typing import Any

from app.models.booking_email_event import BookingEmailEvent
from app.models.price_record import PriceRecord
from app.storage.sqlite_store import append_rows


class IngestionRepositoryMixin:
    def load_price_records(self) -> list[PriceRecord]:
        return self._load_models("SELECT * FROM price_records ORDER BY rowid", PriceRecord)

    def load_booking_email_events(self) -> list[BookingEmailEvent]:
        return self._load_models(
            "SELECT * FROM booking_email_events ORDER BY received_at DESC, rowid DESC",
            BookingEmailEvent,
        )

    def load_booking_email_message_ids(self) -> set[str]:
        rows = self._fetch_rows("SELECT gmail_message_id FROM booking_email_events")
        return {str(row["gmail_message_id"]) for row in rows if row.get("gmail_message_id")}

    def get_booking_email_event_by_message_id(self, gmail_message_id: str) -> BookingEmailEvent | None:
        rows = self._fetch_rows(
            "SELECT * FROM booking_email_events WHERE gmail_message_id = ? LIMIT 1",
            (gmail_message_id,),
        )
        if not rows:
            return None
        return BookingEmailEvent.model_validate(rows[0])

    def load_retryable_booking_email_events(
        self,
        *,
        max_retry_attempts: int,
        limit: int | None = None,
    ) -> list[BookingEmailEvent]:
        query = """
            SELECT *
            FROM booking_email_events
            WHERE processing_status = 'error'
              AND retryable = 1
              AND extraction_attempt_count < ?
            ORDER BY received_at ASC, rowid ASC
        """
        params: tuple[Any, ...] = (max_retry_attempts,)
        if limit is not None:
            query = f"{query}\nLIMIT ?"
            params = (max_retry_attempts, limit)
        return self._load_models(query, BookingEmailEvent, params)

    def upsert_booking_email_event(self, event: BookingEmailEvent) -> None:
        self._upsert_table(
            "booking_email_events",
            [event.model_dump(mode="json")],
            conflict_columns=("email_event_id",),
        )

    def append_booking_email_events(self, events: list[BookingEmailEvent]) -> None:
        if not events:
            return
        self.ensure_data_dir()
        rows = [item.model_dump(mode="json") for item in events]
        with self._borrow_connection() as (connection, own_connection):
            append_rows(connection, "booking_email_events", rows)
            if own_connection:
                connection.commit()

    def append_price_records(self, records: list[PriceRecord]) -> None:
        if not records:
            return
        self.ensure_data_dir()
        rows = [item.model_dump(mode="json", by_alias=True) for item in records]
        with self._borrow_connection() as (connection, own_connection):
            append_rows(connection, "price_records", rows)
            if own_connection:
                connection.commit()
