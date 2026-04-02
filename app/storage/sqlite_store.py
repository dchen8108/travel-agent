from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from app.storage.sqlite_schema import CREATE_PRICE_RECORDS_TABLE, DDL_STATEMENTS, SCHEMA_VERSION


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    _migrate_price_records_to_v3(connection)
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


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row[1]) for row in rows]
