from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from app.models.base import AppState
from app.settings import Settings
from app.storage.repository import Repository
from app.storage.sqlite_schema import DDL_STATEMENTS, SCHEMA_VERSION
from app.storage.sqlite_store import initialize_schema


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


def test_repository_initializes_default_app_state_when_config_missing(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    repository = Repository(settings)
    repository.ensure_data_dir()

    assert repository.load_app_state() == AppState()
    assert repository.app_state_path.exists()


def test_repository_load_app_state_reads_checked_in_shape_from_config_json(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    repository = Repository(settings)
    repository.ensure_data_dir()
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    repository.app_state_path.write_text(
        """
        {
          "dashboard_needs_booking_window_weeks": 5,
          "dashboard_overbooked_window_days": 9,
          "fetch_interval_seconds": 900,
          "launchd_fetch_interval_seconds": 120,
          "launchd_fetch_max_targets": 4
        }
        """.strip(),
        encoding="utf-8",
    )

    app_state = repository.load_app_state()

    assert app_state.dashboard_needs_booking_window_weeks == 5
    assert app_state.dashboard_overbooked_window_days == 9
    assert app_state.fetch_interval_seconds == 900
    assert app_state.launchd_fetch_interval_seconds == 120
    assert app_state.launchd_fetch_max_targets == 4


def test_initialize_schema_skips_legacy_migrations_for_current_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "travel_agent.sqlite3"
    connection = sqlite3.connect(db_path)
    try:
        for statement in DDL_STATEMENTS:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()

        statements: list[str] = []
        connection.set_trace_callback(statements.append)
        initialize_schema(connection)
        connection.set_trace_callback(None)
    finally:
        connection.close()

    forbidden_prefixes = (
        "ALTER TABLE",
        "DROP TABLE",
        "UPDATE ",
        "INSERT INTO rule_group_targets",
        "INSERT INTO trip_instance_group_memberships",
        "INSERT INTO trip_groups",
    )
    forbidden = [
        statement
        for statement in statements
        if statement.startswith(forbidden_prefixes)
    ]
    assert forbidden == []


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

    assert user_version == SCHEMA_VERSION
    assert "data_scope" in columns
    assert "price_text" not in columns
    assert "summary" not in columns
    assert "request_offer_count" not in columns
    assert "is_request_cheapest" not in columns
    assert "record_signature" not in columns


def test_repository_repairs_gmail_booking_prices_with_decimal_cents(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.data_dir / "travel_agent.sqlite3")
    try:
        connection.execute("PRAGMA user_version = 4")
        connection.execute(
            """
            CREATE TABLE bookings (
                booking_id TEXT PRIMARY KEY,
                source TEXT NOT NULL DEFAULT 'manual',
                trip_instance_id TEXT NULL,
                airline TEXT NOT NULL,
                origin_airport TEXT NOT NULL,
                destination_airport TEXT NOT NULL,
                departure_date TEXT NOT NULL,
                departure_time TEXT NOT NULL,
                arrival_time TEXT NOT NULL DEFAULT '',
                booked_price INTEGER NOT NULL,
                record_locator TEXT NOT NULL DEFAULT '',
                booked_at TEXT NOT NULL,
                booking_status TEXT NOT NULL DEFAULT 'active',
                match_status TEXT NOT NULL DEFAULT 'matched',
                raw_summary TEXT NOT NULL DEFAULT '',
                candidate_trip_instance_ids TEXT NOT NULL DEFAULT '',
                resolution_status TEXT NOT NULL DEFAULT 'resolved',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE booking_email_events (
                email_event_id TEXT PRIMARY KEY,
                gmail_message_id TEXT NOT NULL UNIQUE,
                gmail_thread_id TEXT NOT NULL DEFAULT '',
                gmail_history_id TEXT NOT NULL DEFAULT '',
                from_address TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                received_at TEXT NOT NULL,
                processing_status TEXT NOT NULL,
                email_kind TEXT NOT NULL DEFAULT 'unknown',
                extraction_confidence REAL NOT NULL DEFAULT 0,
                extracted_payload_json TEXT NOT NULL DEFAULT '',
                result_booking_ids TEXT NOT NULL DEFAULT '',
                result_unmatched_booking_ids TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO bookings (
                booking_id, source, trip_instance_id, airline, origin_airport, destination_airport,
                departure_date, departure_time, arrival_time, booked_price, record_locator, booked_at, booking_status,
                match_status, raw_summary, candidate_trip_instance_ids, resolution_status, notes, created_at, updated_at
            ) VALUES (
                'book_bad', 'gmail', 'inst_1', 'WN', 'LAX', 'SFO',
                '2026-04-20', '06:00', '07:30', 7840, 'BDJ594', '2026-04-01T12:00:00+00:00', 'active',
                'matched', '', '', 'resolved', '', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO booking_email_events (
                email_event_id, gmail_message_id, gmail_thread_id, gmail_history_id, from_address, subject, received_at,
                processing_status, email_kind, extraction_confidence, extracted_payload_json, result_booking_ids,
                result_unmatched_booking_ids, notes, created_at, updated_at
            ) VALUES (
                'mail_1', 'gmail_1', 'thread_1', '123', 'test@example.com', 'Booking', '2026-04-01T12:00:00+00:00',
                'resolved_auto', 'booking_confirmation', 0.92,
                '{"email_kind":"booking_confirmation","confidence":0.92,"record_locator":"BDJ594","currency":"USD","total_price":7840,"passenger_names":["Test"],"summary":"Total paid $78.40 USD.","notes":"","legs":[{"airline":"WN","origin_airport":"LAX","destination_airport":"SFO","departure_date":"2026-04-20","departure_time":"06:00","arrival_time":"07:30","flight_number":"1105","leg_status":"booked","fare_class":"basic","evidence":"Total $78.40"}]}',
                'book_bad', '', '', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    repository = Repository(settings)
    repository.ensure_data_dir()

    saved_booking = repository.load_bookings()[0]
    assert saved_booking.booked_price == Decimal("78.40")
    assert saved_booking.route_option_id == ""

    connection = sqlite3.connect(repository.db_path)
    try:
        booked_price = connection.execute("SELECT booked_price FROM bookings WHERE booking_id = 'book_bad'").fetchone()[0]
        booking_columns = {row[1]: row[2] for row in connection.execute("PRAGMA table_info(bookings)").fetchall()}
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        booking_email_event_columns = {row[1] for row in connection.execute("PRAGMA table_info(booking_email_events)").fetchall()}
    finally:
        connection.close()

    assert booked_price == 78.4
    assert booking_columns["booked_price"] == "REAL"
    assert booking_columns["route_option_id"] == "TEXT"
    assert user_version == SCHEMA_VERSION
    assert "extraction_attempt_count" in booking_email_event_columns
    assert "retryable" in booking_email_event_columns
    assert "data_scope" in booking_email_event_columns


def test_repository_does_not_repair_gmail_booking_price_again_after_manual_edit(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.data_dir / "travel_agent.sqlite3")
    try:
        connection.execute("PRAGMA user_version = 4")
        connection.execute(
            """
            CREATE TABLE bookings (
                booking_id TEXT PRIMARY KEY,
                source TEXT NOT NULL DEFAULT 'manual',
                trip_instance_id TEXT NULL,
                airline TEXT NOT NULL,
                origin_airport TEXT NOT NULL,
                destination_airport TEXT NOT NULL,
                departure_date TEXT NOT NULL,
                departure_time TEXT NOT NULL,
                arrival_time TEXT NOT NULL DEFAULT '',
                booked_price INTEGER NOT NULL,
                record_locator TEXT NOT NULL DEFAULT '',
                booked_at TEXT NOT NULL,
                booking_status TEXT NOT NULL DEFAULT 'active',
                match_status TEXT NOT NULL DEFAULT 'matched',
                raw_summary TEXT NOT NULL DEFAULT '',
                candidate_trip_instance_ids TEXT NOT NULL DEFAULT '',
                resolution_status TEXT NOT NULL DEFAULT 'resolved',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE booking_email_events (
                email_event_id TEXT PRIMARY KEY,
                gmail_message_id TEXT NOT NULL UNIQUE,
                gmail_thread_id TEXT NOT NULL DEFAULT '',
                gmail_history_id TEXT NOT NULL DEFAULT '',
                from_address TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                received_at TEXT NOT NULL,
                processing_status TEXT NOT NULL,
                email_kind TEXT NOT NULL DEFAULT 'unknown',
                extraction_confidence REAL NOT NULL DEFAULT 0,
                extracted_payload_json TEXT NOT NULL DEFAULT '',
                result_booking_ids TEXT NOT NULL DEFAULT '',
                result_unmatched_booking_ids TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO bookings (
                booking_id, source, trip_instance_id, airline, origin_airport, destination_airport,
                departure_date, departure_time, arrival_time, booked_price, record_locator, booked_at, booking_status,
                match_status, raw_summary, candidate_trip_instance_ids, resolution_status, notes, created_at, updated_at
            ) VALUES (
                'book_manual', 'gmail', 'inst_1', 'WN', 'LAX', 'SFO',
                '2026-04-20', '06:00', '07:30', 7840, 'BDJ594', '2026-04-01T12:00:00+00:00', 'active',
                'matched', '', '', 'resolved', '', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO booking_email_events (
                email_event_id, gmail_message_id, gmail_thread_id, gmail_history_id, from_address, subject, received_at,
                processing_status, email_kind, extraction_confidence, extracted_payload_json, result_booking_ids,
                result_unmatched_booking_ids, notes, created_at, updated_at
            ) VALUES (
                'mail_1', 'gmail_1', 'thread_1', '123', 'test@example.com', 'Booking', '2026-04-01T12:00:00+00:00',
                'resolved_auto', 'booking_confirmation', 0.92,
                '{"email_kind":"booking_confirmation","confidence":0.92,"record_locator":"BDJ594","currency":"USD","total_price":7840,"passenger_names":["Test"],"summary":"Total paid $78.40 USD.","notes":"","legs":[{"airline":"WN","origin_airport":"LAX","destination_airport":"SFO","departure_date":"2026-04-20","departure_time":"06:00","arrival_time":"07:30","flight_number":"1105","leg_status":"booked","fare_class":"basic","evidence":"Total $78.40"}]}',
                'book_manual', '', '', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    repository = Repository(settings)
    repository.ensure_data_dir()

    booking = next(item for item in repository.load_bookings() if item.booking_id == "book_manual")
    assert booking.booked_price == Decimal("78.40")

    booking.booked_price = Decimal("95.40")
    repository.upsert_bookings([booking])

    fresh_repository = Repository(settings)
    fresh_repository.ensure_data_dir()
    reloaded = next(item for item in fresh_repository.load_bookings() if item.booking_id == "book_manual")
    assert reloaded.booked_price == Decimal("95.40")


def test_repository_backfills_obvious_qa_rows_as_test_scope(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    repository = Repository(settings)
    repository.ensure_data_dir()

    connection = sqlite3.connect(repository.db_path)
    try:
        connection.execute(
            """
            INSERT INTO trips (
                trip_id, label, trip_kind, preference_mode, data_scope, active, anchor_date, anchor_weekday, created_at, updated_at
            ) VALUES (
                'trip_test', 'SQLite E2E Trip abc123', 'one_time', 'equal', 'live', 1, '2026-04-15', '', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO trip_instances (
                trip_instance_id, trip_id, display_label, anchor_date, data_scope, instance_kind, booking_id, last_signal_at, created_at, updated_at
            ) VALUES (
                'inst_test', 'trip_test', 'SQLite E2E Trip abc123', '2026-04-15', 'live', 'standalone', '', NULL, '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO bookings (
                booking_id, source, trip_instance_id, data_scope, airline, origin_airport, destination_airport,
                departure_date, departure_time, arrival_time, booked_price, record_locator, booked_at, booking_status,
                match_status, raw_summary, candidate_trip_instance_ids, resolution_status, notes, created_at, updated_at
            ) VALUES (
                'book_test', 'manual', 'inst_test', 'live', 'AS', 'BUR', 'SFO',
                '2026-04-15', '07:00', '08:30', 145.0, 'E2EX123', '2026-04-01T12:00:00+00:00', 'active',
                'matched', '', '', 'resolved', '', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        connection.execute("PRAGMA user_version = 6")
        connection.commit()
    finally:
        connection.close()

    repository = Repository(settings)
    repository.ensure_data_dir()

    trip = next(item for item in repository.load_trips() if item.trip_id == "trip_test")
    trip_instance = next(item for item in repository.load_trip_instances() if item.trip_instance_id == "inst_test")
    booking = next(item for item in repository.load_bookings() if item.booking_id == "book_test")

    assert trip.data_scope == "test"
    assert trip_instance.data_scope == "test"
    assert trip_instance.booking_id == ""
    assert booking.data_scope == "test"


def test_repository_migrates_trips_table_to_relaxed_label_rules(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.data_dir / "travel_agent.sqlite3")
    try:
        connection.execute("PRAGMA user_version = 9")
        connection.execute(
            """
            CREATE TABLE trips (
                trip_id TEXT PRIMARY KEY,
                label TEXT NOT NULL UNIQUE,
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
                trip_id, label, trip_kind, preference_mode, data_scope, active, anchor_date, anchor_weekday, created_at, updated_at
            ) VALUES (
                'trip_1', 'Conference Arrival', 'one_time', 'equal', 'live', 1, '2026-05-10', '', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    repository = Repository(settings)
    repository.ensure_data_dir()

    connection = sqlite3.connect(repository.db_path)
    try:
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        duplicate_insert = connection.execute(
            """
            INSERT INTO trips (
                trip_id, label, trip_kind, preference_mode, data_scope, active, anchor_date, anchor_weekday, created_at, updated_at
            ) VALUES (
                'trip_2', 'Conference Arrival', 'one_time', 'equal', 'live', 1, '2026-05-12', '', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        assert duplicate_insert.rowcount == 1
        inactive_insert = connection.execute(
            """
            INSERT INTO trips (
                trip_id, label, trip_kind, preference_mode, data_scope, active, anchor_date, anchor_weekday, created_at, updated_at
            ) VALUES (
                'trip_3', 'Conference Arrival', 'one_time', 'equal', 'live', 0, '2026-05-10', '', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        assert inactive_insert.rowcount == 1
        connection.execute(
            """
            INSERT INTO trips (
                trip_id, label, trip_kind, preference_mode, data_scope, active, anchor_date, anchor_weekday, created_at, updated_at
            ) VALUES (
                'trip_4', 'Work Commute', 'weekly', 'equal', 'live', 1, NULL, 'Monday', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        try:
            connection.execute(
                """
                INSERT INTO trips (
                    trip_id, label, trip_kind, preference_mode, data_scope, active, anchor_date, anchor_weekday, created_at, updated_at
                ) VALUES (
                    'trip_5', 'Work Commute', 'weekly', 'equal', 'live', 1, NULL, 'Tuesday', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
                )
                """
            )
        except sqlite3.IntegrityError:
            duplicate_weekly_conflict = True
        else:
            duplicate_weekly_conflict = False
    finally:
        connection.close()

    assert user_version == SCHEMA_VERSION
    assert duplicate_weekly_conflict is True


def test_repository_drops_legacy_trip_group_column_and_clears_manual_tracker_signals(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.data_dir / "travel_agent.sqlite3")
    try:
        connection.execute("PRAGMA user_version = 18")
        connection.execute(
            """
            CREATE TABLE trips (
                trip_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                trip_kind TEXT NOT NULL,
                preference_mode TEXT NOT NULL,
                trip_group_id TEXT NOT NULL DEFAULT '',
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
                trip_id, label, trip_kind, preference_mode, trip_group_id, data_scope,
                active, anchor_date, anchor_weekday, created_at, updated_at
            ) VALUES (
                'trip_rule', 'Weekly commute', 'weekly', 'equal', 'grp_legacy', 'live',
                1, NULL, 'Monday', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE trackers (
                tracker_id TEXT PRIMARY KEY,
                trip_instance_id TEXT NOT NULL,
                route_option_id TEXT NOT NULL,
                rank INTEGER NOT NULL,
                data_scope TEXT NOT NULL DEFAULT 'live',
                preference_bias_dollars INTEGER NOT NULL,
                origin_airports TEXT NOT NULL,
                destination_airports TEXT NOT NULL,
                airlines TEXT NOT NULL,
                day_offset INTEGER NOT NULL,
                travel_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                fare_class_policy TEXT NOT NULL,
                provider TEXT NOT NULL,
                last_signal_at TEXT NULL,
                latest_observed_price INTEGER NULL,
                latest_fetched_at TEXT NULL,
                latest_winning_origin_airport TEXT NOT NULL DEFAULT '',
                latest_winning_destination_airport TEXT NOT NULL DEFAULT '',
                latest_signal_source TEXT NOT NULL DEFAULT '',
                latest_match_summary TEXT NOT NULL DEFAULT '',
                definition_signature TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO trackers (
                tracker_id, trip_instance_id, route_option_id, rank, data_scope, preference_bias_dollars,
                origin_airports, destination_airports, airlines, day_offset, travel_date, start_time,
                end_time, fare_class_policy, provider, last_signal_at, latest_observed_price,
                latest_fetched_at, latest_winning_origin_airport, latest_winning_destination_airport,
                latest_signal_source, latest_match_summary, definition_signature, created_at, updated_at
            ) VALUES (
                'trk_1', 'inst_1', 'opt_1', 1, 'live', 0, 'BUR', 'SFO', 'AS', 0, '2026-04-06',
                '06:00', '10:00', 'include_basic', 'google_flights', '2026-04-01T12:00:00+00:00',
                199, '2026-04-01T12:00:00+00:00', 'BUR', 'SFO', 'manual_import', 'Legacy import',
                'sig_1', '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    repository = Repository(settings)
    repository.ensure_data_dir()
    assert [item.trip_id for item in repository.load_trips()] == ["trip_rule"]
    assert repository.load_trackers()[0].latest_signal_source == ""
    assert repository.load_trackers()[0].latest_observed_price is None

    connection = sqlite3.connect(repository.db_path)
    try:
        trip_columns = [row[1] for row in connection.execute("PRAGMA table_info(trips)")]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()

    assert user_version == SCHEMA_VERSION
    assert "trip_group_id" not in trip_columns
