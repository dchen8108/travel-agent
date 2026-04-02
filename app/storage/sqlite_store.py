from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from app.money import normalize_extracted_total_price
from app.storage.sqlite_schema import CREATE_BOOKINGS_TABLE, CREATE_PRICE_RECORDS_TABLE, DDL_STATEMENTS, SCHEMA_VERSION


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    _migrate_bookings_to_v5(connection)
    _migrate_booking_email_events_to_v6(connection)
    _migrate_price_records_to_v3(connection)
    _migrate_data_scope_to_v7(connection)
    _migrate_bookings_to_v8(connection)
    for statement in DDL_STATEMENTS:
        connection.execute(statement)
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    connection.commit()


def fetch_all(
    connection: sqlite3.Connection,
    query: str,
    params: Sequence[Any] = (),
) -> list[dict[str, Any]]:
    rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def replace_rows(
    connection: sqlite3.Connection,
    table: str,
    rows: Iterable[dict[str, Any]],
    *,
    where_sql: str | None = None,
    where_params: Sequence[Any] = (),
) -> None:
    rows = list(rows)
    if where_sql:
        connection.execute(f"DELETE FROM {table} WHERE {where_sql}", where_params)
    else:
        connection.execute(f"DELETE FROM {table}")
    if not rows:
        return
    _insert_rows(connection, table, rows)


def append_rows(
    connection: sqlite3.Connection,
    table: str,
    rows: Iterable[dict[str, Any]],
) -> None:
    rows = list(rows)
    if not rows:
        return
    _insert_rows(connection, table, rows)


def upsert_singleton_row(
    connection: sqlite3.Connection,
    table: str,
    row: dict[str, Any],
) -> None:
    _insert_rows(connection, table, [row], replace=True)


def table_has_rows(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
    return row is not None


@contextmanager
def immediate_transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


def _insert_rows(
    connection: sqlite3.Connection,
    table: str,
    rows: list[dict[str, Any]],
    *,
    replace: bool = False,
) -> None:
    columns = list(rows[0].keys())
    quoted_columns = ", ".join(columns)
    placeholders = ", ".join(["?"] * len(columns))
    insert_keyword = "INSERT OR REPLACE" if replace else "INSERT"
    query = f"{insert_keyword} INTO {table} ({quoted_columns}) VALUES ({placeholders})"
    values = [[row.get(column) for column in columns] for row in rows]
    connection.executemany(query, values)


def _migrate_price_records_to_v3(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "price_records"):
        return
    columns = _table_columns(connection, "price_records")
    desired_columns = {
        "price_record_id",
        "fetch_event_id",
        "observed_at",
        "fetch_target_id",
        "tracker_id",
        "trip_instance_id",
        "trip_id",
        "route_option_id",
        "tracker_definition_signature",
        "tracker_rank",
        "search_origin_airports",
        "search_destination_airports",
        "search_airlines",
        "search_day_offset",
        "search_travel_date",
        "search_start_time",
        "search_end_time",
        "search_fare_class_policy",
        "query_origin_airport",
        "query_destination_airport",
        "airline",
        "departure_label",
        "arrival_label",
        "price",
        "offer_rank",
    }
    if set(columns) == desired_columns:
        return

    connection.execute("ALTER TABLE price_records RENAME TO price_records_old")
    connection.execute(CREATE_PRICE_RECORDS_TABLE.replace("IF NOT EXISTS ", ""))
    connection.execute(
        """
        INSERT INTO price_records (
            price_record_id,
            fetch_event_id,
            observed_at,
            fetch_target_id,
            tracker_id,
            trip_instance_id,
            trip_id,
            route_option_id,
            tracker_definition_signature,
            tracker_rank,
            search_origin_airports,
            search_destination_airports,
            search_airlines,
            search_day_offset,
            search_travel_date,
            search_start_time,
            search_end_time,
            search_fare_class_policy,
            query_origin_airport,
            query_destination_airport,
            airline,
            departure_label,
            arrival_label,
            price,
            offer_rank
        )
        SELECT
            price_record_id,
            fetch_event_id,
            observed_at,
            fetch_target_id,
            tracker_id,
            trip_instance_id,
            trip_id,
            route_option_id,
            tracker_definition_signature,
            tracker_rank,
            search_origin_airports,
            search_destination_airports,
            search_airlines,
            search_day_offset,
            search_travel_date,
            search_start_time,
            search_end_time,
            search_fare_class_policy,
            query_origin_airport,
            query_destination_airport,
            airline,
            COALESCE(departure_label, ''),
            COALESCE(arrival_label, ''),
            price,
            COALESCE(offer_rank, 1)
        FROM price_records_old
        """
    )
    connection.execute("DROP TABLE price_records_old")


def _migrate_bookings_to_v5(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "bookings"):
        return
    columns = _table_columns(connection, "bookings")
    needs_rebuild = "booked_price" in columns and _column_type(connection, "bookings", "booked_price") != "REAL"
    if needs_rebuild:
        connection.execute("ALTER TABLE bookings RENAME TO bookings_old")
        connection.execute(CREATE_BOOKINGS_TABLE.replace("IF NOT EXISTS ", ""))
        connection.execute(
            """
            INSERT INTO bookings (
                booking_id,
                source,
                trip_instance_id,
                data_scope,
                airline,
                origin_airport,
                destination_airport,
                departure_date,
                departure_time,
                arrival_time,
                booked_price,
                record_locator,
                booked_at,
                booking_status,
                match_status,
                raw_summary,
                candidate_trip_instance_ids,
                resolution_status,
                notes,
                created_at,
                updated_at
            )
            SELECT
                booking_id,
                source,
                trip_instance_id,
                'live',
                airline,
                origin_airport,
                destination_airport,
                departure_date,
                departure_time,
                arrival_time,
                booked_price,
                record_locator,
                booked_at,
                booking_status,
                match_status,
                raw_summary,
                candidate_trip_instance_ids,
                resolution_status,
                notes,
                created_at,
                updated_at
            FROM bookings_old
            """
        )
        connection.execute("DROP TABLE bookings_old")
    _repair_gmail_booking_prices_to_v5(connection)


def _migrate_bookings_to_v8(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "bookings"):
        return
    columns = _table_columns(connection, "bookings")
    if "tracker_id" not in columns:
        return

    connection.execute("ALTER TABLE bookings RENAME TO bookings_old_v8")
    connection.execute(CREATE_BOOKINGS_TABLE.replace("IF NOT EXISTS ", ""))
    connection.execute(
        """
        INSERT INTO bookings (
            booking_id,
            source,
            trip_instance_id,
            data_scope,
            airline,
            origin_airport,
            destination_airport,
            departure_date,
            departure_time,
            arrival_time,
            booked_price,
            record_locator,
            booked_at,
            booking_status,
            match_status,
            raw_summary,
            candidate_trip_instance_ids,
            resolution_status,
            notes,
            created_at,
            updated_at
        )
        SELECT
            booking_id,
            source,
            trip_instance_id,
            COALESCE(data_scope, 'live'),
            airline,
            origin_airport,
            destination_airport,
            departure_date,
            departure_time,
            arrival_time,
            booked_price,
            record_locator,
            booked_at,
            booking_status,
            match_status,
            raw_summary,
            candidate_trip_instance_ids,
            resolution_status,
            notes,
            created_at,
            updated_at
        FROM bookings_old_v8
        """
    )
    connection.execute("DROP TABLE bookings_old_v8")


def _migrate_booking_email_events_to_v6(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "booking_email_events"):
        return
    columns = _table_columns(connection, "booking_email_events")
    if "extraction_attempt_count" not in columns:
        connection.execute(
            "ALTER TABLE booking_email_events ADD COLUMN extraction_attempt_count INTEGER NOT NULL DEFAULT 0"
        )
    if "retryable" not in columns:
        connection.execute(
            "ALTER TABLE booking_email_events ADD COLUMN retryable INTEGER NOT NULL DEFAULT 1"
        )
    connection.execute(
        """
        UPDATE booking_email_events
        SET retryable = 0
        WHERE processing_status = 'error'
          AND (
            LOWER(notes) LIKE '%request too large%'
            OR LOWER(notes) LIKE '%input or output tokens must be reduced%'
            OR LOWER(notes) LIKE '%maximum context length%'
            OR LOWER(notes) LIKE '%context length%'
          )
        """
    )


def _migrate_data_scope_to_v7(connection: sqlite3.Connection) -> None:
    scope_tables = (
        "trips",
        "route_options",
        "trip_instances",
        "trackers",
        "tracker_fetch_targets",
        "bookings",
        "booking_email_events",
        "price_records",
    )
    for table in scope_tables:
        if not _table_exists(connection, table):
            continue
        columns = _table_columns(connection, table)
        if "data_scope" not in columns:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN data_scope TEXT NOT NULL DEFAULT 'live'"
            )

    if _table_exists(connection, "trips"):
        connection.execute(
            """
            UPDATE trips
            SET data_scope = 'test'
            WHERE label LIKE 'QA %'
               OR label LIKE 'SQLite E2E %'
               OR label LIKE 'E2E %'
            """
        )
    if _table_exists(connection, "route_options") and _table_exists(connection, "trips"):
        connection.execute(
            """
            UPDATE route_options
            SET data_scope = 'test'
            WHERE trip_id IN (SELECT trip_id FROM trips WHERE data_scope = 'test')
            """
        )
    if _table_exists(connection, "trip_instances") and _table_exists(connection, "trips"):
        connection.execute(
            """
            UPDATE trip_instances
            SET data_scope = 'test'
            WHERE trip_id IN (SELECT trip_id FROM trips WHERE data_scope = 'test')
            """
        )
    if _table_exists(connection, "trackers") and _table_exists(connection, "trip_instances"):
        connection.execute(
            """
            UPDATE trackers
            SET data_scope = 'test'
            WHERE trip_instance_id IN (
                SELECT trip_instance_id FROM trip_instances WHERE data_scope = 'test'
            )
            """
        )
    if _table_exists(connection, "tracker_fetch_targets") and _table_exists(connection, "trackers"):
        connection.execute(
            """
            UPDATE tracker_fetch_targets
            SET data_scope = 'test'
            WHERE tracker_id IN (
                SELECT tracker_id FROM trackers WHERE data_scope = 'test'
            )
            """
        )
    if _table_exists(connection, "price_records") and _table_exists(connection, "trips"):
        connection.execute(
            """
            UPDATE price_records
            SET data_scope = 'test'
            WHERE trip_id IN (SELECT trip_id FROM trips WHERE data_scope = 'test')
            """
        )
    if _table_exists(connection, "bookings"):
        conditions = ["record_locator LIKE 'E2E%'", "raw_summary LIKE '%E2E%'"]
        if _table_exists(connection, "trip_instances"):
            conditions.insert(
                0,
                """
                trip_instance_id IN (
                    SELECT trip_instance_id FROM trip_instances WHERE data_scope = 'test'
                )
                """.strip(),
            )
        connection.execute(
            f"""
            UPDATE bookings
            SET data_scope = 'test'
            WHERE {' OR '.join(conditions)}
            """
        )
    if _table_exists(connection, "booking_email_events") and _table_exists(connection, "bookings"):
        connection.execute(
            """
            UPDATE booking_email_events
            SET data_scope = 'test'
            WHERE EXISTS (
                SELECT 1
                FROM bookings
                WHERE bookings.data_scope = 'test'
                  AND (
                    instr('|' || booking_email_events.result_booking_ids || '|', '|' || bookings.booking_id || '|') > 0
                    OR instr('|' || booking_email_events.result_unmatched_booking_ids || '|', '|' || bookings.booking_id || '|') > 0
                  )
            )
            """
        )


def _repair_gmail_booking_prices_to_v5(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "booking_email_events"):
        return
    rows = connection.execute(
        """
        SELECT extracted_payload_json, result_booking_ids, result_unmatched_booking_ids
        FROM booking_email_events
        WHERE processing_status IN ('resolved_auto', 'needs_resolution')
          AND (result_booking_ids != '' OR result_unmatched_booking_ids != '')
        """
    ).fetchall()
    for row in rows:
        repaired = _repaired_event_booked_price(
            extracted_payload_json=str(row["extracted_payload_json"] or ""),
        )
        if repaired is None:
            continue
        booking_ids = [item for item in str(row["result_booking_ids"] or "").split("|") if item]
        unmatched_ids = [item for item in str(row["result_unmatched_booking_ids"] or "").split("|") if item]
        for booking_id in booking_ids + unmatched_ids:
            connection.execute(
                "UPDATE bookings SET booked_price = ? WHERE booking_id = ? AND source = 'gmail'",
                (float(repaired), booking_id),
            )


def _repaired_event_booked_price(*, extracted_payload_json: str) -> float | None:
    if not extracted_payload_json:
        return None
    try:
        payload = json.loads(extracted_payload_json)
    except json.JSONDecodeError:
        return None
    legs = payload.get("legs", []) or []
    if len(legs) > 1:
        return 0.0
    repaired = normalize_extracted_total_price(
        payload.get("total_price"),
        context_texts=[
            str(payload.get("summary", "")),
            str(payload.get("notes", "")),
            *(str(leg.get("evidence", "")) for leg in legs if isinstance(leg, dict)),
        ],
    )
    if repaired is None:
        return None
    return float(repaired)


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def _column_type(connection: sqlite3.Connection, table: str, column: str) -> str:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    for row in rows:
        if str(row[1]) == column:
            return str(row[2]).upper()
    return ""
