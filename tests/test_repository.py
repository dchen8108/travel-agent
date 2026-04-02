from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from app.models.base import AppState
from app.models.booking_email_event import BookingEmailEvent
from app.models.route_option import RouteOption
from app.models.rule_group_target import RuleGroupTarget
from app.models.trip import Trip
from app.models.trip_group import TripGroup
from app.models.trip_instance import TripInstance
from app.models.trip_instance_group_membership import TripInstanceGroupMembership
from app.settings import Settings
from app.storage.csv_store import save_csv_models
from app.storage.json_store import save_json_model
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

    assert user_version == 14
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
    assert user_version == 14
    assert "extraction_attempt_count" in booking_email_event_columns
    assert "retryable" in booking_email_event_columns
    assert "data_scope" in booking_email_event_columns


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
                trip_instance_id, trip_id, display_label, anchor_date, data_scope, instance_kind, travel_state, booking_id, last_signal_at, created_at, updated_at
            ) VALUES (
                'inst_test', 'trip_test', 'SQLite E2E Trip abc123', '2026-04-15', 'live', 'standalone', 'open', '', NULL, '2026-04-01T12:00:00+00:00', '2026-04-01T12:00:00+00:00'
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
        connection.execute("PRAGMA user_version = 7")
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
    assert trip_instance.travel_state == "planned"
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

    assert user_version == 14
    assert duplicate_weekly_conflict is True


def test_repository_imports_current_legacy_tables_when_bootstrapping_sqlite(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    save_json_model(settings.data_dir / "app.json", AppState())

    group = TripGroup(trip_group_id="grp_1", label="Work travel")
    rule = Trip(
        trip_id="trip_rule",
        label="Weekly commute",
        trip_kind="weekly",
        anchor_weekday="Monday",
    )
    instance = TripInstance(
        trip_instance_id="inst_1",
        trip_id="trip_rule",
        display_label="Weekly commute (2026-04-06)",
        anchor_date="2026-04-06",
        instance_kind="generated",
        recurring_rule_trip_id="trip_rule",
        rule_occurrence_date="2026-04-06",
        inheritance_mode="attached",
    )
    target = RuleGroupTarget(rule_trip_id="trip_rule", trip_group_id="grp_1")
    membership = TripInstanceGroupMembership(
        trip_instance_id="inst_1",
        trip_group_id="grp_1",
        membership_source="inherited",
        source_rule_trip_id="trip_rule",
    )
    event = BookingEmailEvent(
        email_event_id="mail_1",
        gmail_message_id="gmail_1",
        subject="Booking confirmation",
        processing_status="ignored",
    )

    save_csv_models(settings.data_dir / "trip_groups.csv", [group], list(TripGroup.model_fields))
    save_csv_models(settings.data_dir / "trips.csv", [rule], list(Trip.model_fields))
    save_csv_models(settings.data_dir / "route_options.csv", [], list(RouteOption.model_fields))
    save_csv_models(settings.data_dir / "trip_instances.csv", [instance], list(TripInstance.model_fields))
    save_csv_models(settings.data_dir / "rule_group_targets.csv", [target], list(RuleGroupTarget.model_fields))
    save_csv_models(
        settings.data_dir / "trip_instance_group_memberships.csv",
        [membership],
        list(TripInstanceGroupMembership.model_fields),
    )
    save_csv_models(
        settings.data_dir / "booking_email_events.csv",
        [event],
        list(BookingEmailEvent.model_fields),
    )

    repository = Repository(settings)
    repository.ensure_data_dir()

    assert [item.trip_group_id for item in repository.load_trip_groups()] == ["grp_1"]
    assert [(item.rule_trip_id, item.trip_group_id) for item in repository.load_rule_group_targets()] == [
        ("trip_rule", "grp_1")
    ]
    assert [
        (item.trip_instance_id, item.trip_group_id, item.membership_source)
        for item in repository.load_trip_instance_group_memberships()
    ] == [("inst_1", "grp_1", "inherited")]
    assert [item.gmail_message_id for item in repository.load_booking_email_events()] == ["gmail_1"]
