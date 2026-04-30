from __future__ import annotations

from typing import Any

from app.models.booking_email_event import BookingEmailEvent
from app.models.price_record import PriceRecord
from app.storage.sqlite_store import append_rows


class IngestionRepositoryMixin:
    def load_price_records(self) -> list[PriceRecord]:
        return self._load_models("SELECT * FROM price_records ORDER BY rowid", PriceRecord)

    def load_price_records_for_fetch_targets_at_times(
        self,
        fetch_target_observed_at: list[tuple[str, str]],
    ) -> list[PriceRecord]:
        if not fetch_target_observed_at:
            return []
        deduped_pairs = list(dict.fromkeys(
            (fetch_target_id.strip(), observed_at.strip())
            for fetch_target_id, observed_at in fetch_target_observed_at
            if fetch_target_id and observed_at
        ))
        if not deduped_pairs:
            return []
        params: list[str] = []
        for fetch_target_id, observed_at in deduped_pairs:
            params.extend([fetch_target_id, observed_at])
        values = ", ".join("(?, ?)" for _fetch_target_id, _observed_at in deduped_pairs)
        query = f"""
            WITH latest(fetch_target_id, observed_at) AS (
                VALUES {values}
            )
            SELECT *
            FROM price_records
            WHERE EXISTS (
                SELECT 1
                FROM latest
                WHERE latest.fetch_target_id = price_records.fetch_target_id
                  AND latest.observed_at = price_records.observed_at
            )
            ORDER BY observed_at DESC, price ASC, offer_rank ASC, rowid ASC
        """
        return self._load_models(query, PriceRecord, tuple(params))

    def load_booking_email_events(self) -> list[BookingEmailEvent]:
        return self._load_models(
            "SELECT * FROM booking_email_events ORDER BY received_at DESC, rowid DESC",
            BookingEmailEvent,
        )

    def existing_booking_email_message_ids(
        self,
        gmail_message_ids: list[str],
        *,
        batch_size: int = 500,
    ) -> set[str]:
        deduped_ids = list(dict.fromkeys(
            gmail_message_id.strip()
            for gmail_message_id in gmail_message_ids
            if gmail_message_id and gmail_message_id.strip()
        ))
        if not deduped_ids:
            return set()

        existing_ids: set[str] = set()
        for start in range(0, len(deduped_ids), batch_size):
            batch = deduped_ids[start:start + batch_size]
            placeholders = ", ".join("?" for _ in batch)
            rows = self._fetch_rows(
                f"SELECT gmail_message_id FROM booking_email_events WHERE gmail_message_id IN ({placeholders})",
                tuple(batch),
            )
            existing_ids.update(
                str(row["gmail_message_id"])
                for row in rows
                if row.get("gmail_message_id")
            )
        return existing_ids

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
