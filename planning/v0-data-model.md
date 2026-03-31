# travel-agent v0 Data Model

## Storage Strategy

Use local files only.

For v0, store record lists as CSV files because they are easy to inspect and back up. Use one small JSON file for app-level metadata.

Suggested layout:

```text
data/
  app.json
  trips.csv
  route_options.csv
  trip_instances.csv
  trackers.csv
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
- isolate Google Flights specifics to trackers, email events, and observations

## `app.json`

Purpose:

- local metadata and defaults

Suggested fields:

```json
{
  "timezone": "America/Los_Angeles",
  "future_weeks": 12,
  "email_ingestion_mode": "manual_upload",
  "version": 2
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

Notes:

- `label` must be unique
- `trip_kind` is `one_time` or `weekly`
- `anchor_date` is used by one-time trips
- `anchor_weekday` is used by weekly trips and defines the rolling weekly anchor day

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
- `day_offset` is an integer, typically `-1`, `0`, or `1`
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

Notes:

- weekly trips maintain the next 12 future instances
- skipping one occurrence should set `travel_state = skipped`
- recommendation state is distinct from travel state

## `trackers.csv`

Purpose:

- operational Google Flights tracker rows for a specific route option on a specific trip instance

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
- `latest_match_summary`
- `created_at`
- `updated_at`

Allowed `provider` values:

- `google_flights`

Allowed `link_source` values:

- `generated`
- `manual`

Allowed `tracking_status` values:

- `needs_setup`
- `tracking_enabled`
- `signal_received`
- `stale`

Notes:

- a tracker is a search envelope, not a single concrete itinerary
- actual observed itineraries belong in `fare_observations.csv`

## `bookings.csv`

Purpose:

- store user bookings that have been attached to a trip instance

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

Allowed `status` values:

- `active`
- `rebooked`

Notes:

- a booking should attach to the best matching tracker when possible
- `tracker_id` may be empty if the trip instance match is known but tracker match is unclear

## `unmatched_bookings.csv`

Purpose:

- hold bookings that could not be attached confidently

One row per unresolved booking.

Suggested columns:

- `unmatched_booking_id`
- `source`
- `airline`
- `origin_airport`
- `destination_airport`
- `departure_date`
- `departure_time`
- `arrival_time`
- `booked_price`
- `record_locator`
- `raw_summary`
- `candidate_trip_instance_ids`
- `resolution_status`
- `created_at`
- `updated_at`

Allowed `source` values:

- `manual`
- `email_import`

Allowed `resolution_status` values:

- `open`
- `resolved`

Notes:

- only unmatched bookings should surface in `Resolve`
- unmatched tracker observations should never create rows here

## `email_events.csv`

Purpose:

- keep a record of imported Google Flights emails

One row per `.eml` import.

Suggested columns:

- `email_event_id`
- `provider`
- `source_message_id`
- `received_at`
- `subject`
- `parsed_status`
- `observation_count`
- `matched_observation_count`
- `imported_email_path`
- `raw_excerpt`
- `created_at`

Allowed `parsed_status` values:

- `parsed`
- `parsed_with_ignored_observations`
- `failed`

Notes:

- the email event exists for debugging and history
- ignored observations should not create user-facing review work

## `fare_observations.csv`

Purpose:

- store concrete price observations extracted from Google Flights emails

One row per accepted matched observation.

Suggested columns:

- `fare_observation_id`
- `email_event_id`
- `tracker_id`
- `trip_instance_id`
- `observed_at`
- `airline`
- `origin_airport`
- `destination_airport`
- `travel_date`
- `departure_time`
- `arrival_time`
- `price`
- `previous_price`
- `price_direction`
- `match_summary`
- `created_at`

Notes:

- only confidently matched observations should be stored here
- ambiguous or unmatched tracker observations should be ignored
- trip-level recommendation logic should rely on the best latest observations per tracker envelope
