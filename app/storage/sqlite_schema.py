from __future__ import annotations

SCHEMA_VERSION = 7


CREATE_BOOKINGS_TABLE = """
CREATE TABLE IF NOT EXISTS bookings (
    booking_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'manual',
    trip_instance_id TEXT NULL,
    data_scope TEXT NOT NULL DEFAULT 'live',
    tracker_id TEXT NULL,
    airline TEXT NOT NULL,
    origin_airport TEXT NOT NULL,
    destination_airport TEXT NOT NULL,
    departure_date TEXT NOT NULL,
    departure_time TEXT NOT NULL,
    arrival_time TEXT NOT NULL DEFAULT '',
    booked_price REAL NOT NULL,
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


CREATE_PRICE_RECORDS_TABLE = """
CREATE TABLE IF NOT EXISTS price_records (
    price_record_id TEXT PRIMARY KEY,
    fetch_event_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    data_scope TEXT NOT NULL DEFAULT 'live',
    fetch_target_id TEXT NOT NULL,
    tracker_id TEXT NOT NULL,
    trip_instance_id TEXT NOT NULL,
    trip_id TEXT NOT NULL,
    route_option_id TEXT NOT NULL,
    tracker_definition_signature TEXT NOT NULL,
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
    airline TEXT NOT NULL,
    departure_label TEXT NOT NULL DEFAULT '',
    arrival_label TEXT NOT NULL DEFAULT '',
    price INTEGER NOT NULL,
    offer_rank INTEGER NOT NULL
)
"""


DDL_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS trips (
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
    """,
    """
    CREATE TABLE IF NOT EXISTS route_options (
        route_option_id TEXT PRIMARY KEY,
        trip_id TEXT NOT NULL,
        rank INTEGER NOT NULL,
        data_scope TEXT NOT NULL DEFAULT 'live',
        savings_needed_vs_previous INTEGER NOT NULL,
        origin_airports TEXT NOT NULL,
        destination_airports TEXT NOT NULL,
        airlines TEXT NOT NULL,
        day_offset INTEGER NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        fare_class_policy TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trip_instances (
        trip_instance_id TEXT PRIMARY KEY,
        trip_id TEXT NOT NULL,
        display_label TEXT NOT NULL,
        anchor_date TEXT NOT NULL,
        data_scope TEXT NOT NULL DEFAULT 'live',
        instance_kind TEXT NOT NULL,
        travel_state TEXT NOT NULL,
        booking_id TEXT NOT NULL DEFAULT '',
        last_signal_at TEXT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trackers (
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
    """,
    """
    CREATE TABLE IF NOT EXISTS tracker_fetch_targets (
        fetch_target_id TEXT PRIMARY KEY,
        tracker_id TEXT NOT NULL,
        trip_instance_id TEXT NOT NULL,
        data_scope TEXT NOT NULL DEFAULT 'live',
        tracker_definition_signature TEXT NOT NULL DEFAULT '',
        origin_airport TEXT NOT NULL,
        destination_airport TEXT NOT NULL,
        schedule_offset_seconds INTEGER NOT NULL,
        google_flights_url TEXT NOT NULL,
        last_fetch_started_at TEXT NULL,
        last_fetch_finished_at TEXT NULL,
        last_fetch_status TEXT NOT NULL,
        last_fetch_error TEXT NOT NULL DEFAULT '',
        consecutive_failures INTEGER NOT NULL DEFAULT 0,
        next_fetch_not_before TEXT NULL,
        latest_price INTEGER NULL,
        latest_airline TEXT NOT NULL DEFAULT '',
        latest_departure_label TEXT NOT NULL DEFAULT '',
        latest_arrival_label TEXT NOT NULL DEFAULT '',
        latest_summary TEXT NOT NULL DEFAULT '',
        latest_fetched_at TEXT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    CREATE_BOOKINGS_TABLE,
    """
    CREATE TABLE IF NOT EXISTS booking_email_events (
        email_event_id TEXT PRIMARY KEY,
        gmail_message_id TEXT NOT NULL UNIQUE,
        data_scope TEXT NOT NULL DEFAULT 'live',
        gmail_thread_id TEXT NOT NULL DEFAULT '',
        gmail_history_id TEXT NOT NULL DEFAULT '',
        from_address TEXT NOT NULL DEFAULT '',
        subject TEXT NOT NULL DEFAULT '',
        received_at TEXT NOT NULL,
        processing_status TEXT NOT NULL,
        email_kind TEXT NOT NULL DEFAULT 'unknown',
        extraction_confidence REAL NOT NULL DEFAULT 0,
        extraction_attempt_count INTEGER NOT NULL DEFAULT 0,
        retryable INTEGER NOT NULL DEFAULT 1,
        extracted_payload_json TEXT NOT NULL DEFAULT '',
        result_booking_ids TEXT NOT NULL DEFAULT '',
        result_unmatched_booking_ids TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    CREATE_PRICE_RECORDS_TABLE,
    "CREATE INDEX IF NOT EXISTS idx_trips_label ON trips(label)",
    "CREATE INDEX IF NOT EXISTS idx_route_options_trip_rank ON route_options(trip_id, rank)",
    "CREATE INDEX IF NOT EXISTS idx_trip_instances_trip_anchor ON trip_instances(trip_id, anchor_date)",
    "CREATE INDEX IF NOT EXISTS idx_trip_instances_anchor_state ON trip_instances(anchor_date, travel_state)",
    "CREATE INDEX IF NOT EXISTS idx_trackers_trip_instance_rank ON trackers(trip_instance_id, rank)",
    "CREATE INDEX IF NOT EXISTS idx_tracker_fetch_targets_due ON tracker_fetch_targets(next_fetch_not_before, last_fetch_status)",
    "CREATE INDEX IF NOT EXISTS idx_tracker_fetch_targets_tracker_pair ON tracker_fetch_targets(tracker_id, origin_airport, destination_airport)",
    "CREATE INDEX IF NOT EXISTS idx_bookings_trip_status ON bookings(trip_instance_id, booking_status, booked_at)",
    "CREATE INDEX IF NOT EXISTS idx_bookings_match_status ON bookings(match_status, departure_date)",
    "CREATE INDEX IF NOT EXISTS idx_bookings_record_locator ON bookings(record_locator)",
    "CREATE INDEX IF NOT EXISTS idx_booking_email_events_status_received ON booking_email_events(processing_status, received_at)",
    "CREATE INDEX IF NOT EXISTS idx_booking_email_events_received ON booking_email_events(received_at)",
    "CREATE INDEX IF NOT EXISTS idx_price_records_fetch_target_observed ON price_records(fetch_target_id, observed_at)",
    "CREATE INDEX IF NOT EXISTS idx_price_records_tracker_observed ON price_records(tracker_id, observed_at)",
    "CREATE INDEX IF NOT EXISTS idx_price_records_trip_instance_observed ON price_records(trip_instance_id, observed_at)",
)
