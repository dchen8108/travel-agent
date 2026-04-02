# SQLite Storage

`travel-agent` now uses a local SQLite database at `data/travel_agent.sqlite3`.
App-level config lives separately in `config/app_state.json`.

The migration strategy is pragmatic:

- keep the current model and repository API stable
- store the same logical objects in SQLite tables
- import legacy CSV/JSON files automatically on first boot when the database does not exist yet
- keep `price_records` append-only

`config/app_state.json` is the source of truth for:

- `timezone`
- `future_weeks`
- `enable_background_fetcher`
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
- `travel_state`
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
- `tracker_id`
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

### `price_records`

Append-only fact table.

One successful fetch can create many rows, one per returned offer.

Key columns:

- `price_record_id`
- `fetch_event_id`
- `observed_at`
- `observed_date`
- `source`
- `provider`
- `fetch_method`
- `fetch_target_id`
- `tracker_id`
- `trip_instance_id`
- `trip_id`
- `route_option_id`
- `tracker_definition_signature`
- `trip_label`
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
- `google_flights_url`
- `airline`
- `departure_label`
- `arrival_label`
- `price`
- `price_text`
- `summary`
- `offer_rank`
- `request_offer_count`
- `is_request_cheapest`
- `record_signature`
- `created_at`

## Relationships

Logical ownership remains:

- `Trip 1 -> N RouteOption`
- `Trip 1 -> N TripInstance`
- `TripInstance 1 -> N Tracker`
- `RouteOption 1 -> N Tracker`
- `Tracker 1 -> N TrackerFetchTarget`
- `TripInstance 1 -> N Booking`
- `TrackerFetchTarget 1 -> N PriceRecord`

For this first migration, those relationships are maintained primarily by the repository and domain services rather than deep SQL normalization. That keeps the product stable while moving off CSVs.

## Runtime Notes

- The repository API is unchanged.
- `sync_and_persist()` and the background fetch persistence path now write through SQLite transactions.
- The launchd worker continues to use the same one-shot batch job; only the storage backend changed.
