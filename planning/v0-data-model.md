# travel-agent v0 Data Model

## Storage Strategy

Use local files only.

For v0, store record lists as CSV files because they are easy to inspect and back up. Use one small JSON file for app-level metadata.

```text
data/
  app.json
  trips.csv
  route_options.csv
  trip_instances.csv
  trackers.csv
  tracker_fetch_targets.csv
  bookings.csv
  unmatched_bookings.csv
  email_events.csv
  fare_observations.csv
  imported_emails/
```

## Design Goals

- easy to inspect manually
- easy to reset during development
- enough structure to support recurring generation and booking linkage
- isolate Google Flights specifics to trackers, fetch targets, email events, and observations

## `app.json`

Purpose:

- local metadata and feature flags

Suggested fields:

```json
{
  "timezone": "America/Los_Angeles",
  "future_weeks": 12,
  "email_ingestion_mode": "manual_upload",
  "enable_background_fetcher": true,
  "enable_manual_imports": true,
  "version": 3
}
```

## `trips.csv`

Purpose:

- persistent top-level trip definitions

One row per trip label.

Suggested columns:

- `trip_id`
- `label`
- `trip_kind`
- `active`
- `anchor_date`
- `anchor_weekday`
- `created_at`
- `updated_at`

## `route_options.csv`

Purpose:

- ranked tracker definitions under a trip

One row per route option.

Suggested columns:

- `route_option_id`
- `trip_id`
- `rank`
- `origin_airports`
- `destination_airports`
- `airlines`
- `day_offset`
- `start_time`
- `end_time`
- `created_at`
- `updated_at`

Notes:

- store airport and airline selections as `|`-delimited values
- `day_offset` is typically `-1`, `0`, or `1`
- cap origin airports at 3
- cap destination airports at 3
- all route options are implicitly nonstop-only in v0

## `trip_instances.csv`

Purpose:

- dated occurrences generated from trips

One row per trip occurrence.

Suggested columns:

- `trip_instance_id`
- `trip_id`
- `display_label`
- `anchor_date`
- `instance_kind`
- `travel_state`
- `recommendation_state`
- `recommendation_reason`
- `booking_id`
- `last_signal_at`
- `created_at`
- `updated_at`

Allowed `travel_state` values:

- `open`
- `booked`
- `skipped`

Allowed `recommendation_state` values:

- `needs_tracker_setup`
- `wait`
- `book_now`
- `booked_monitoring`
- `rebook`

## `trackers.csv`

Purpose:

- operational tracker rows for a specific route option on a specific trip instance

One row per route option per trip instance.

Suggested columns:

- `tracker_id`
- `trip_instance_id`
- `route_option_id`
- `rank`
- `origin_airports`
- `destination_airports`
- `airlines`
- `day_offset`
- `travel_date`
- `start_time`
- `end_time`
- `provider`
- `link_source`
- `tracking_status`
- `google_flights_url`
- `tracking_enabled_at`
- `last_signal_at`
- `latest_observed_price`
- `latest_fetched_at`
- `latest_winning_origin_airport`
- `latest_winning_destination_airport`
- `latest_signal_source`
- `latest_match_summary`
- `created_at`
- `updated_at`

Allowed `tracking_status` values:

- `needs_setup`
- `tracking_enabled`
- `signal_received`
- `stale`

Allowed `latest_signal_source` values:

- `manual_import`
- `background_fetch`

Notes:

- a tracker is a search envelope, not a single concrete itinerary
- actual airport-pair fetches belong in `tracker_fetch_targets.csv`
- email-based historical observations still belong in `fare_observations.csv`

## `tracker_fetch_targets.csv`

Purpose:

- store the concrete airport-pair Google Flights search state under each tracker

One row per tracker + origin airport + destination airport.

Suggested columns:

- `fetch_target_id`
- `tracker_id`
- `trip_instance_id`
- `origin_airport`
- `destination_airport`
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

Allowed `last_fetch_status` values:

- `pending`
- `success`
- `failed`

Notes:

- one tracker can fan out to at most 9 fetch targets
- fetch targets are the background polling unit
- the tracker keeps the rolled-up best known price

## `bookings.csv`

Purpose:

- store user bookings attached to a trip instance

One row per attached booking.

Suggested columns:

- `booking_id`
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
- `status`
- `notes`
- `created_at`
- `updated_at`

## `unmatched_bookings.csv`

Purpose:

- hold bookings that could not be attached confidently

One row per unresolved booking.

## `email_events.csv` and `fare_observations.csv`

Purpose:

- preserve the legacy manual-import path

These tables remain in v0 as a fallback path while the in-house Google Flights fetcher proves itself out.
