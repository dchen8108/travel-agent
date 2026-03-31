# travel-agent v0 Data Model

## Storage Strategy

Use local files only.

For v0, prefer CSV files for record lists because they are easy to inspect and can be opened in Excel or Numbers. Use one small JSON file for app-level metadata that does not fit naturally into CSV.

Suggested future folder:

```text
data/
  app.json
  programs.csv
  trip_instances.csv
  trackers.csv
  bookings.csv
  email_events.csv
  fare_observations.csv
  review_items.csv
  imported_emails/
```

## Design Goals

- easy to inspect manually
- easy to back up with git
- simple enough to edit outside the app if needed
- enough structure to support end-to-end recommendations

## 1. `app.json`

Purpose:

- local metadata and defaults

Suggested fields:

```json
{
  "timezone": "America/Los_Angeles",
  "default_lookahead_weeks": 8,
  "default_rebook_alert_threshold": 20,
  "email_ingestion_mode": "manual_upload",
  "version": 1
}
```

## 2. `programs.csv`

Purpose:

- define recurring flight rules

One row per recurring rule.

Suggested columns:

- `program_id`
- `program_name`
- `active`
- `trip_mode`
- `origin_airports`
- `destination_airports`
- `outbound_weekday`
- `outbound_time_start`
- `outbound_time_end`
- `return_weekday`
- `return_time_start`
- `return_time_end`
- `preferred_airlines`
- `allowed_airlines`
- `fare_preference`
- `nonstop_only`
- `lookahead_weeks`
- `rebook_alert_threshold`
- `created_at`
- `updated_at`

Notes:

- store airport and airline lists as pipe-delimited strings, for example `BUR|LAX|SNA`
- store booleans as `true` or `false`
- `trip_mode` is `one_way` or `round_trip`
- for one-way rules, return fields stay blank

Example:

```csv
program_id,program_name,active,trip_mode,origin_airports,destination_airports,outbound_weekday,outbound_time_start,outbound_time_end,return_weekday,return_time_start,return_time_end,preferred_airlines,allowed_airlines,fare_preference,nonstop_only,lookahead_weeks,rebook_alert_threshold,created_at,updated_at
prog_001,LA to SF Outbound,true,one_way,BUR|LAX|SNA,SFO,Monday,06:00,10:00,,,,Alaska|United|Delta,Alaska|United|Delta|Southwest,flexible,true,8,20,2026-03-31T09:00:00-07:00,2026-03-31T09:00:00-07:00
```

## 3. `trip_instances.csv`

Purpose:

- represent concrete future trips generated from recurring rules

One row per concrete trip. A one-way rule generates one-way trips, while a round-trip rule generates outbound/return pairs.

Suggested columns:

- `trip_instance_id`
- `program_id`
- `trip_mode`
- `origin_airport`
- `destination_airport`
- `outbound_date`
- `return_date`
- `status`
- `recommendation_reason`
- `best_airline`
- `best_fare_type`
- `best_price`
- `best_outbound_summary`
- `best_return_summary`
- `outbound_tracker_id`
- `return_tracker_id`
- `last_checked_at`
- `dismissed_until`
- `booking_id`
- `created_at`
- `updated_at`

Allowed `status` values:

- `needs_tracker_setup`
- `not_ready`
- `wait`
- `book_now`
- `booked_monitoring`
- `rebook`

Notes:

- `booking_id` is empty until the user records a booking
- `outbound_tracker_id` and `return_tracker_id` point to segment trackers when they exist
- this table drives the Today and Calendar screens
- a round-trip recommendation should be computed from the latest safe outbound and return observations
- a one-way recommendation should be computed from the latest safe outbound observation
- `return_date`, `best_return_summary`, and `return_tracker_id` can be blank for one-way trips

Example:

```csv
trip_instance_id,program_id,trip_mode,origin_airport,destination_airport,outbound_date,return_date,status,recommendation_reason,best_airline,best_fare_type,best_price,best_outbound_summary,best_return_summary,outbound_tracker_id,return_tracker_id,last_checked_at,dismissed_until,booking_id,created_at,updated_at
trip_001,prog_001,one_way,BUR,SFO,2026-05-12,,book_now,Current fare is near the best observed price for this trip.,Alaska,flexible,186,AS123 07:00-08:35,,trk_001,,2026-04-04T08:05:00-07:00,,,2026-03-31T09:00:00-07:00,2026-04-04T08:05:00-07:00
```

## 4. `trackers.csv`

Purpose:

- track Google Flights links and tracker readiness per trip segment

One row per outbound or return segment that should be monitored in Google Flights.

Suggested columns:

- `tracker_id`
- `trip_instance_id`
- `segment_type`
- `origin_airport`
- `destination_airport`
- `travel_date`
- `provider`
- `link_source`
- `tracking_status`
- `google_flights_url`
- `tracking_enabled_at`
- `last_signal_at`
- `latest_observed_price`
- `created_at`
- `updated_at`

Allowed `provider` values:

- `google_flights`

Allowed `segment_type` values:

- `outbound`
- `return`

Allowed `link_source` values:

- `generated`
- `manual`

Allowed `tracking_status` values:

- `needs_setup`
- `tracking_enabled`
- `signal_received`
- `stale`

Example:

```csv
tracker_id,trip_instance_id,segment_type,origin_airport,destination_airport,travel_date,provider,link_source,tracking_status,google_flights_url,tracking_enabled_at,last_signal_at,latest_observed_price,created_at,updated_at
trk_001,trip_001,outbound,BUR,SFO,2026-05-12,google_flights,manual,signal_received,https://www.google.com/travel/flights/search?... ,2026-04-01T18:00:00-07:00,2026-04-04T08:02:00-07:00,186,2026-03-31T09:00:00-07:00,2026-04-04T08:02:00-07:00
```

## 5. `bookings.csv`

Purpose:

- store the trips the user actually booked

One row per booked trip instance.

Suggested columns:

- `booking_id`
- `trip_instance_id`
- `airline`
- `fare_type`
- `booked_price`
- `booked_at`
- `outbound_summary`
- `return_summary`
- `record_locator`
- `status`
- `notes`
- `created_at`
- `updated_at`

Allowed `status` values:

- `active`
- `cancelled`
- `rebooked`

Notes:

- `trip_instance_id` should point back to the generated trip
- if the user rebooks, the prior row can be marked `rebooked` and a fresh booking row can be created
- keep the required fields minimal so manual entry is fast

Example:

```csv
booking_id,trip_instance_id,airline,fare_type,booked_price,booked_at,outbound_summary,return_summary,record_locator,status,notes,created_at,updated_at
book_001,trip_004,United,flexible,224,2026-04-03T07:20:00-07:00,UA123 07:00-08:31,UA456 18:10-19:40,ABC123,active,Booked after alert,2026-04-03T07:20:00-07:00,2026-04-03T07:20:00-07:00
```

## 6. `email_events.csv`

Purpose:

- keep a raw-ish record of ingested Google Flights emails
- support debugging when parsing fails or mapping is ambiguous

One row per ingested email.

Suggested columns:

- `email_event_id`
- `provider`
- `source_message_id`
- `received_at`
- `subject`
- `parsed_status`
- `observation_count`
 - `imported_email_path`
 - `raw_excerpt`
 - `created_at`

Allowed `provider` values:

- `google_flights_email`

Allowed `parsed_status` values:

- `parsed`
- `unmatched`
- `needs_review`

Example:

```csv
email_event_id,provider,source_message_id,received_at,subject,parsed_status,observation_count,imported_email_path,raw_excerpt,created_at
mail_001,google_flights_email,<abc123@example.com>,2026-04-04T08:02:00-07:00,Prices for your tracked flights have changed,parsed,3,imported_emails/mail_001.eml,San Francisco to Burbank ... Los Angeles to New York ... New York to Los Angeles,2026-04-04T08:02:10-07:00
```

## 7. `fare_observations.csv`

Purpose:

- store price snapshots over time
- support explanations and rebook checks

One row per observed fare option at a point in time.

Suggested columns:

- `observation_id`
- `tracker_id`
- `trip_instance_id`
- `segment_type`
- `source_type`
- `source_id`
- `observed_at`
- `airline`
- `fare_type`
- `price`
- `outbound_summary`
- `return_summary`
- `is_best_current_option`

Notes:

- keep this table append-only
- the best current option for a trip is derived from the latest observation set
- most v0 observations will come from parsed Google Flights emails
- if a parsed observation cannot be matched safely, it should not appear here until manual review resolves it

Example:

```csv
observation_id,tracker_id,trip_instance_id,segment_type,source_type,source_id,observed_at,airline,fare_type,price,outbound_summary,return_summary,is_best_current_option
obs_001,trk_001,trip_001,outbound,google_flights_email,mail_001,2026-04-04T08:02:00-07:00,Alaska,flexible,186,AS123 07:00-08:35,,true
```

## 8. `review_items.csv`

Purpose:

- hold ambiguous or unmatched parsed observations until the user resolves them

One row per parsed observation that needs a human decision.

Suggested columns:

- `review_item_id`
- `email_event_id`
- `observed_route`
- `observed_date`
- `observed_airline`
- `observed_price`
- `status`
- `resolution_notes`
- `resolved_tracker_id`
- `created_at`
- `resolved_at`

Allowed `status` values:

- `open`
- `resolved`
- `ignored`

## Relationships

Core relationships:

- one `program` generates many `trip_instances`
- one `trip_instance` should have up to two segment `trackers`
- one `trip_instance` may have zero or one active `booking`
- one `email_event` may produce many `fare_observations`
- one `email_event` may also produce many `review_items`
- one `trip_instance` may have many `fare_observations`

## Minimal Logic Supported By This Model

This model is enough to:

- generate upcoming commute weeks
- generate and track Google Flights segment monitoring links
- ingest Google Flights email alerts
- store current segment observations and roll them up into a trip recommendation
- record a booking
- compare booked trip price against the combined current segment price
- show recent price history
- preserve ambiguous imports without losing evidence

## Intentional Omissions

v0 does not model:

- credits
- hotels
- seat assignments
- baggage details
- multiple travelers
- loyalty programs
- refund rules beyond the high-level fare type
- direct live-search provider sessions
- automatic Gmail sync
- outbound email delivery

Those can be added later if the core booking and rebooking loop proves valuable.
