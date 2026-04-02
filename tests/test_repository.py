from __future__ import annotations

import sqlite3
from pathlib import Path

from app.models.base import AppState
from app.settings import Settings
from app.storage.repository import Repository


def test_repository_stores_app_state_in_config_json(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    repository = Repository(settings)
    repository.ensure_data_dir()
    app_state = AppState(
        timezone="America/New_York",
        future_weeks=16,
        enable_background_fetcher=False,
        version=5,
    )

    repository.save_app_state(app_state)

    assert repository.app_state_path.exists()
    assert repository.load_app_state() == app_state

    connection = sqlite3.connect(repository.db_path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        connection.close()
    assert "app_state" not in tables


def test_repository_bootstraps_app_state_from_existing_db_row_when_config_missing(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.data_dir / "travel_agent.sqlite3")
    try:
        connection.execute(
            """
            CREATE TABLE app_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                timezone TEXT NOT NULL,
                future_weeks INTEGER NOT NULL,
                enable_background_fetcher INTEGER NOT NULL,
                version INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO app_state (id, timezone, future_weeks, enable_background_fetcher, version)
            VALUES (1, 'America/Chicago', 9, 0, 4)
            """
        )
        connection.commit()
    finally:
        connection.close()

    repository = Repository(settings)
    repository.ensure_data_dir()

    assert repository.load_app_state() == AppState(
        timezone="America/Chicago",
        future_weeks=9,
        enable_background_fetcher=False,
        version=4,
    )
    assert repository.app_state_path.exists()

    connection = sqlite3.connect(repository.db_path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        connection.close()
    assert "app_state" not in tables


def test_repository_migrates_existing_price_records_table_to_slim_schema(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.data_dir / "travel_agent.sqlite3")
    try:
        connection.execute("PRAGMA user_version = 2")
        connection.execute(
            """
            CREATE TABLE price_records (
                price_record_id TEXT PRIMARY KEY,
                fetch_event_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                observed_date TEXT NULL,
                source TEXT NOT NULL,
                provider TEXT NOT NULL,
                fetch_method TEXT NOT NULL,
                fetch_target_id TEXT NOT NULL,
                tracker_id TEXT NOT NULL,
                trip_instance_id TEXT NOT NULL,
                trip_id TEXT NOT NULL,
                route_option_id TEXT NOT NULL,
                tracker_definition_signature TEXT NOT NULL,
                trip_label TEXT NOT NULL DEFAULT '',
                tracker_rank INTEGER NOT NULL,
                search_origin_airports TEXT NOT NULL,
                search_destination_airports TEXT NOT NULL,
                search_airlines TEXT NOT NULL,
                search_day_offset INTEGER NOT NULL,
                search_travel_date TEXT NOT NULL,
                search_start_time TEXT NOT NULL,
                search_end_time TEXT NOT NULL,
                search_fare_class_policy TEXT NOT NULL,
                query_origin_airport TEXT NOT NULL,
                query_destination_airport TEXT NOT NULL,
                google_flights_url TEXT NOT NULL DEFAULT '',
                airline TEXT NOT NULL,
                departure_label TEXT NOT NULL DEFAULT '',
                arrival_label TEXT NOT NULL DEFAULT '',
                price INTEGER NOT NULL,
                price_text TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                offer_rank INTEGER NOT NULL,
                request_offer_count INTEGER NOT NULL,
                is_request_cheapest INTEGER NOT NULL DEFAULT 0,
                record_signature TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO price_records (
                price_record_id, fetch_event_id, observed_at, observed_date, source, provider, fetch_method,
                fetch_target_id, tracker_id, trip_instance_id, trip_id, route_option_id, tracker_definition_signature,
                trip_label, tracker_rank, search_origin_airports, search_destination_airports, search_airlines,
                search_day_offset, search_travel_date, search_start_time, search_end_time, search_fare_class_policy,
                query_origin_airport, query_destination_airport, google_flights_url, airline, departure_label,
                arrival_label, price, price_text, summary, offer_rank, request_offer_count, is_request_cheapest,
                record_signature, created_at
            ) VALUES (
                'price_1', 'fetch_1', '2026-04-01T12:00:00+00:00', '2026-04-01', 'background_fetch', 'google_flights',
                'generated_link', 'ft_1', 'trk_1', 'inst_1', 'trip_1', 'opt_1', 'sig_1', 'Legacy label', 1, 'BUR',
                'SFO', 'Alaska', 0, '2026-04-20', '06:00', '10:00', 'include_basic', 'BUR', 'SFO',
                'https://www.google.com/travel/flights/search?tfs=old', 'Alaska', '6:00 AM', '7:30 AM', 199, '$199',
                'Legacy summary', 1, 2, 1, 'record_sig', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    repository = Repository(settings)
    repository.ensure_data_dir()

    saved_records = repository.load_price_records()
    assert len(saved_records) == 1
    assert saved_records[0].price_record_id == "price_1"
    assert saved_records[0].price == 199
    assert saved_records[0].offer_rank == 1
    assert saved_records[0].query_origin_airport == "BUR"

    connection = sqlite3.connect(repository.db_path)
    try:
        columns = [
            row[1]
            for row in connection.execute("PRAGMA table_info(price_records)")
        ]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()

    assert user_version == 3
    assert "price_text" not in columns
    assert "summary" not in columns
    assert "request_offer_count" not in columns
    assert "is_request_cheapest" not in columns
    assert "record_signature" not in columns
