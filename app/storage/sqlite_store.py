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
    _migrate_unmatched_bookings_to_v9(connection)
    _migrate_trips_to_v10(connection)
    _migrate_trip_groups_to_v11(connection)
    _migrate_status_enums_to_v12(connection)
    _migrate_group_memberships_to_v13(connection)
    _migrate_weekly_rule_legacy_groups_to_v14(connection)
    _migrate_fetch_target_claims_to_v15(connection)
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


def delete_rows(
    connection: sqlite3.Connection,
    table: str,
    *,
    where_sql: str,
    where_params: Sequence[Any] = (),
) -> None:
    connection.execute(f"DELETE FROM {table} WHERE {where_sql}", where_params)


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


def upsert_rows(
    connection: sqlite3.Connection,
    table: str,
    rows: Iterable[dict[str, Any]],
    *,
    conflict_columns: Sequence[str],
) -> None:
    rows = list(rows)
    if not rows:
        return
    columns = list(rows[0].keys())
    update_columns = [column for column in columns if column not in conflict_columns]
    if not update_columns:
        raise ValueError("upsert_rows requires at least one non-conflict column.")
    quoted_columns = ", ".join(columns)
    placeholders = ", ".join(["?"] * len(columns))
    conflict_target = ", ".join(conflict_columns)
    assignments = ", ".join(f"{column}=excluded.{column}" for column in update_columns)
    query = (
        f"INSERT INTO {table} ({quoted_columns}) VALUES ({placeholders}) "
        f"ON CONFLICT({conflict_target}) DO UPDATE SET {assignments}"
    )
    values = [[row.get(column) for column in columns] for row in rows]
    connection.executemany(query, values)


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


def _migrate_unmatched_bookings_to_v9(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "bookings"):
        return
    columns = _table_columns(connection, "bookings")
    if "auto_link_enabled" in columns:
        return
    connection.execute(
        "ALTER TABLE bookings ADD COLUMN auto_link_enabled INTEGER NOT NULL DEFAULT 1"
    )


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


def _migrate_trips_to_v10(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "trips"):
        return
    table_sql = (_table_sql(connection, "trips") or "").lower()
    if "label text not null unique" not in table_sql:
        return

    connection.execute("ALTER TABLE trips RENAME TO trips_old_v10")
    connection.execute(
        """
        CREATE TABLE trips (
            trip_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            trip_kind TEXT NOT NULL,
            preference_mode TEXT NOT NULL,
            data_scope TEXT NOT NULL DEFAULT 'live',
            active INTEGER NOT NULL,
            anchor_date TEXT NULL,
            anchor_weekday TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO trips (
            trip_id,
            label,
            trip_kind,
            preference_mode,
            data_scope,
            active,
            anchor_date,
            anchor_weekday,
            created_at,
            updated_at
        )
        SELECT
            trip_id,
            label,
            trip_kind,
            preference_mode,
            COALESCE(data_scope, 'live'),
            active,
            anchor_date,
            anchor_weekday,
            created_at,
            updated_at
        FROM trips_old_v10
        """
    )
    connection.execute("DROP TABLE trips_old_v10")


def _migrate_status_enums_to_v12(connection: sqlite3.Connection) -> None:
    if _table_exists(connection, "trip_instances"):
        connection.execute(
            """
            UPDATE trip_instances
            SET travel_state = 'planned'
            WHERE travel_state = 'open'
            """
        )
    if _table_exists(connection, "bookings"):
        connection.execute(
            """
            UPDATE bookings
            SET booking_status = 'cancelled'
            WHERE booking_status = 'rebooked'
            """
        )


def _migrate_group_memberships_to_v13(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rule_group_targets (
            rule_trip_id TEXT NOT NULL,
            trip_group_id TEXT NOT NULL,
            data_scope TEXT NOT NULL DEFAULT 'live',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (rule_trip_id, trip_group_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trip_instance_group_memberships (
            trip_instance_id TEXT NOT NULL,
            trip_group_id TEXT NOT NULL,
            membership_source TEXT NOT NULL DEFAULT 'manual',
            source_rule_trip_id TEXT NOT NULL DEFAULT '',
            data_scope TEXT NOT NULL DEFAULT 'live',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (trip_instance_id, trip_group_id)
        )
        """
    )
    if not _table_exists(connection, "trips"):
        return

    weekly_rows = connection.execute(
        """
        SELECT trip_id, trip_group_id, data_scope, created_at, updated_at
        FROM trips
        WHERE trip_kind = 'weekly' AND COALESCE(trip_group_id, '') != ''
        """
    ).fetchall()
    for row in weekly_rows:
        connection.execute(
            """
            INSERT OR IGNORE INTO rule_group_targets (
                rule_trip_id,
                trip_group_id,
                data_scope,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                row["trip_id"],
                row["trip_group_id"],
                str(row["data_scope"] or "live"),
                row["created_at"],
                row["updated_at"],
            ),
        )

    if not _table_exists(connection, "trip_instances"):
        return

    rows = connection.execute(
        """
        SELECT
            instances.trip_instance_id,
            instances.inheritance_mode,
            instances.recurring_rule_trip_id,
            instances.data_scope AS instance_data_scope,
            instances.created_at AS instance_created_at,
            instances.updated_at AS instance_updated_at,
            trips.trip_group_id AS trip_group_id,
            trips.data_scope AS trip_data_scope
        FROM trip_instances AS instances
        LEFT JOIN trips ON trips.trip_id = instances.trip_id
        """
    ).fetchall()
    for row in rows:
        instance_id = str(row["trip_instance_id"] or "")
        inheritance_mode = str(row["inheritance_mode"] or "manual")
        if inheritance_mode == "attached" and str(row["recurring_rule_trip_id"] or ""):
            target_rows = connection.execute(
                """
                SELECT trip_group_id, data_scope
                FROM rule_group_targets
                WHERE rule_trip_id = ?
                """,
                (row["recurring_rule_trip_id"],),
            ).fetchall()
            for target_row in target_rows:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO trip_instance_group_memberships (
                        trip_instance_id,
                        trip_group_id,
                        membership_source,
                        source_rule_trip_id,
                        data_scope,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, 'inherited', ?, ?, ?, ?)
                    """,
                    (
                        instance_id,
                        target_row["trip_group_id"],
                        str(row["recurring_rule_trip_id"] or ""),
                        str(target_row["data_scope"] or row["instance_data_scope"] or "live"),
                        row["instance_created_at"],
                        row["instance_updated_at"],
                    ),
                )
            continue

        trip_group_id = str(row["trip_group_id"] or "").strip()
        if not trip_group_id:
            continue
        membership_source = "frozen" if inheritance_mode == "detached" else "manual"
        source_rule_trip_id = str(row["recurring_rule_trip_id"] or "") if inheritance_mode == "detached" else ""
        connection.execute(
            """
            INSERT OR IGNORE INTO trip_instance_group_memberships (
                trip_instance_id,
                trip_group_id,
                membership_source,
                source_rule_trip_id,
                data_scope,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                instance_id,
                trip_group_id,
                membership_source,
                source_rule_trip_id,
                str(row["trip_data_scope"] or row["instance_data_scope"] or "live"),
                row["instance_created_at"],
                row["instance_updated_at"],
            ),
        )


def _migrate_weekly_rule_legacy_groups_to_v14(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "trips"):
        return
    trip_columns = _table_columns(connection, "trips")
    if "trip_group_id" not in trip_columns:
        return
    connection.execute(
        """
        UPDATE trips
        SET trip_group_id = ''
        WHERE trip_kind = 'weekly'
          AND COALESCE(trip_group_id, '') != ''
        """
    )


def _migrate_fetch_target_claims_to_v15(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "tracker_fetch_targets"):
        return
    columns = _table_columns(connection, "tracker_fetch_targets")
    if "fetch_claim_owner" not in columns:
        connection.execute(
            "ALTER TABLE tracker_fetch_targets ADD COLUMN fetch_claim_owner TEXT NOT NULL DEFAULT ''"
        )
    if "fetch_claim_expires_at" not in columns:
        connection.execute(
            "ALTER TABLE tracker_fetch_targets ADD COLUMN fetch_claim_expires_at TEXT NULL"
        )


def _migrate_trip_groups_to_v11(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "trip_groups"):
        connection.execute(
            """
            CREATE TABLE trip_groups (
                trip_group_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                data_scope TEXT NOT NULL DEFAULT 'live',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    if _table_exists(connection, "trips"):
        trip_columns = _table_columns(connection, "trips")
        if "trip_group_id" not in trip_columns:
            connection.execute(
                "ALTER TABLE trips ADD COLUMN trip_group_id TEXT NOT NULL DEFAULT ''"
            )
        weekly_rows = connection.execute(
            """
            SELECT trip_id, label, data_scope, trip_group_id, created_at, updated_at
            FROM trips
            WHERE trip_kind = 'weekly' AND COALESCE(trip_group_id, '') != ''
            """
        ).fetchall()
        for row in weekly_rows:
            trip_group_id = str(row["trip_group_id"] or "").strip()
            if not trip_group_id:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO trip_groups (
                    trip_group_id,
                    label,
                    description,
                    data_scope,
                    created_at,
                    updated_at
                ) VALUES (?, ?, '', ?, ?, ?)
                """,
                (
                    trip_group_id,
                    row["label"],
                    str(row["data_scope"] or "live"),
                    row["created_at"],
                    row["updated_at"],
                ),
            )

    if _table_exists(connection, "trip_instances"):
        instance_columns = _table_columns(connection, "trip_instances")
        if "recurring_rule_trip_id" not in instance_columns:
            connection.execute(
                "ALTER TABLE trip_instances ADD COLUMN recurring_rule_trip_id TEXT NOT NULL DEFAULT ''"
            )
        if "rule_occurrence_date" not in instance_columns:
            connection.execute(
                "ALTER TABLE trip_instances ADD COLUMN rule_occurrence_date TEXT NULL"
            )
        if "inheritance_mode" not in instance_columns:
            connection.execute(
                "ALTER TABLE trip_instances ADD COLUMN inheritance_mode TEXT NOT NULL DEFAULT 'manual'"
            )
        if "deleted" not in instance_columns:
            connection.execute(
                "ALTER TABLE trip_instances ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0"
            )
        connection.execute(
            """
            UPDATE trip_instances
            SET recurring_rule_trip_id = trip_id
            WHERE instance_kind = 'generated'
              AND recurring_rule_trip_id = ''
            """
        )
        connection.execute(
            """
            UPDATE trip_instances
            SET rule_occurrence_date = anchor_date
            WHERE instance_kind = 'generated'
              AND rule_occurrence_date IS NULL
            """
        )
        connection.execute(
            """
            UPDATE trip_instances
            SET inheritance_mode = CASE
                WHEN instance_kind = 'generated' THEN 'attached'
                ELSE 'manual'
            END
            WHERE inheritance_mode IS NULL
               OR inheritance_mode = ''
               OR inheritance_mode = 'manual'
            """
        )


def _migrate_data_scope_to_v7(connection: sqlite3.Connection) -> None:
    scope_tables = (
        "trip_groups",
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


def _table_sql(connection: sqlite3.Connection, table: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if row is None or row[0] is None:
        return ""
    return str(row[0])


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def _column_type(connection: sqlite3.Connection, table: str, column: str) -> str:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    for row in rows:
        if str(row[1]) == column:
            return str(row[2]).upper()
    return ""
