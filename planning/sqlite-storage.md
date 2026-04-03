# SQLite Storage

`travel-agent` now uses a local SQLite database at `data/travel_agent.sqlite3`.
App-level config lives separately in `config/app_state.json`.
Gmail poller config lives in `config/gmail_integration.json`.

The migration strategy is pragmatic:

- keep the current model and repository API stable
- store the same logical objects in SQLite tables
- keep `price_records` append-only

`config/app_state.json` is the source of truth for:

- `timezone`
- `future_weeks`
- `enable_background_fetcher`
- `show_test_data`
- `process_test_data`
- config schema `version`

SQLite itself carries its schema version through `PRAGMA user_version`.

## Logical Tables

### `trips`

Planning parent object.

Key columns:

- `trip_id`
- `label`
- `trip_kind`
- `preference_mode`
- `data_scope`
- `active`
- `anchor_date`
- `anchor_weekday`
- `created_at`
- `updated_at`

### `route_options`

Ranked tracker definitions under a trip.

Key columns:

- `route_option_id`
- `trip_id`
- `rank`
- `data_scope`
- `savings_needed_vs_previous`
- `origin_airports`
- `destination_airports`
- `airlines`
- `day_offset`
- `start_time`
- `end_time`
- `fare_class_policy`
- `created_at`
- `updated_at`

Multi-value airport and airline fields remain pipe-delimited in this first SQLite cutover so the domain layer does not need to change.

### `trip_instances`

Dated operational occurrences of trips.

Key columns:

- `trip_instance_id`
- `trip_id`
- `display_label`
- `anchor_date`
- `instance_kind`
- `recurring_rule_trip_id`
- `rule_occurrence_date`
- `inheritance_mode`
- `deleted`
- `booking_id`
- `last_signal_at`
- `created_at`
- `updated_at`

### `trackers`

One route option instantiated for one trip instance.

Key columns:

- `tracker_id`
- `trip_instance_id`
- `route_option_id`
- `rank`
- `preference_bias_dollars`
- `origin_airports`
- `destination_airports`
- `airlines`
- `day_offset`
- `travel_date`
- `start_time`
- `end_time`
- `fare_class_policy`
- `provider`
- `definition_signature`
- `last_signal_at`
- `latest_observed_price`
- `latest_fetched_at`
- `latest_winning_origin_airport`
- `latest_winning_destination_airport`
- `latest_signal_source`
- `latest_match_summary`
- `created_at`
- `updated_at`

### `tracker_fetch_targets`

Concrete airport-pair Google Flights fetch rows under a tracker.

Key columns:

- `fetch_target_id`
- `tracker_id`
- `trip_instance_id`
- `tracker_definition_signature`
- `origin_airport`
- `destination_airport`
- `schedule_offset_seconds`
- `google_flights_url`
- `last_fetch_started_at`
- `last_fetch_finished_at`
- `last_fetch_status`
- `last_fetch_error`
- `consecutive_failures`
- `next_fetch_not_before`
- `latest_price`
- `latest_airline`
- `latest_departure_label`
- `latest_arrival_label`
- `latest_summary`
- `latest_fetched_at`
- `created_at`
- `updated_at`

This table is the real polling queue for the background fetcher.

### `bookings`

Unified storage for both matched bookings and unresolved bookings.

Matched rows use:

- `match_status = 'matched'`

Unresolved rows use:

- `match_status = 'unmatched'`

Key columns:

- `booking_id`
- `source`
- `trip_instance_id`
- `route_option_id`
- `data_scope`
- `airline`
- `origin_airport`
- `destination_airport`
- `departure_date`
- `departure_time`
- `arrival_time`
- `booked_price`
- `record_locator`
- `booked_at`
- `booking_status`
- `match_status`
- `raw_summary`
- `candidate_trip_instance_ids`
- `resolution_status`
- `notes`
- `created_at`
- `updated_at`

The application still exposes `Booking` and `UnmatchedBooking` models separately through the repository for compatibility, but both are backed by this one table.

Bookings are trip-scoped. They can optionally link to a uniquely matched route option, but booked-vs-current comparison logic is still based on the trip's best current option after preferences are applied.

### `price_records`

Append-only fact table.

One successful fetch can create many rows, one per returned offer.

Key columns:

- `price_record_id`
- `fetch_event_id`
- `observed_at`
- `data_scope`
- `fetch_target_id`
- `tracker_id`
- `trip_instance_id`
- `trip_id`
- `route_option_id`
- `tracker_definition_signature`
- `tracker_rank`
- `search_origin_airports`
- `search_destination_airports`
- `search_airlines`
- `search_day_offset`
- `search_travel_date`
- `search_start_time`
- `search_end_time`
- `search_fare_class_policy`
- `query_origin_airport`
- `query_destination_airport`
- `airline`
- `departure_label`
- `arrival_label`
- `price`
- `offer_rank`

### `booking_email_events`

Append-only audit log for Gmail intake.

Key columns:

- `email_event_id`
- `gmail_message_id`
- `gmail_thread_id`
- `gmail_history_id`
- `from_address`
- `subject`
- `received_at`
- `processing_status`
- `email_kind`
- `extraction_confidence`
- `extracted_payload_json`
- `result_booking_ids`
- `result_unmatched_booking_ids`
- `notes`
- `created_at`
- `updated_at`

## Relationships

Logical ownership remains:

- `Trip 1 -> N RouteOption`
- `Trip 1 -> N TripInstance`
- `TripInstance 1 -> N Tracker`
- `RouteOption 1 -> N Tracker`
- `Tracker 1 -> N TrackerFetchTarget`
- `TripInstance 1 -> N Booking`
- `TrackerFetchTarget 1 -> N PriceRecord`
- `Gmail message 1 -> 1 BookingEmailEvent`

For this first migration, those relationships are maintained primarily by the repository and domain services rather than deep SQL normalization. That keeps the product stable while moving off CSVs.

## Runtime Notes

- The repository API is unchanged.
- `sync_and_persist()` and the background fetch persistence path now write through SQLite transactions.
- The launchd worker continues to use the same one-shot batch job; only the storage backend changed.
