# travel-agent v0 Tech Spec

## Objective

Implement a local-first web app that organizes Google Flights searches and bookings around named trips.

The app should support:

- one-time trips
- weekly recurring trips
- ranked route options
- rolling 12-week instance generation
- conservative in-house Google Flights fetching
- one Google Flights link per airport combination
- automatic booking attachment when confident
- booking-only resolution when not confident

This version intentionally avoids:

- paid fare APIs
- Gmail polling
- a database
- aggressive or synchronous fetching in request paths
- parallel scraping or proxy rotation

## Architecture Summary

v0 consists of six layers:

1. `Web UI`
   FastAPI server-rendered pages for Today, Trips, Bookings, Resolve, and Trackers.

2. `Domain services`
   Trip planning, recurring-instance generation, tracker synchronization, booking attachment, and recommendation rollup.

3. `Fetch orchestration`
   One tracker fans out into concrete airport-pair fetch targets. A small worker selects due targets, adds a small random startup delay, fetches them serially on a 4-hour cadence anchored to the parent trip, and updates tracker rollups.

4. `Storage`
   CSV and JSON files under `data/`.

5. `Historical price logging`
   Every successful Google Flights fetch appends one row per parsed offer into a standalone `price_records.csv` fact table.

6. `Upstream signal source`
   Generated Google Flights search links queried conservatively in the background.

## Stack

- Python 3.12+
- `uv`
- FastAPI
- Jinja2 templates
- lightweight vanilla JS for live filters and trip-form pickers
- Pydantic models
- `httpx`
- `selectolax`
- standard-library CSV, JSON, and `email` modules

## Core Domain Model

### Trip

Persistent parent definition.

Key fields:

- `trip_id`
- `label`
- `trip_kind`
- `active`
- `anchor_date`
- `anchor_weekday`

Rules:

- labels must be unique
- `one_time` trips use `anchor_date`
- `weekly` trips use `anchor_weekday`

### Route Option

Ranked tracker definition under a trip.

Key fields:

- `route_option_id`
- `trip_id`
- `rank`
- `origin_airports`
- `destination_airports`
- `airlines`
- `day_offset`
- `start_time`
- `end_time`

Rules:

- `day_offset` is stored as `-1`, `0`, or `1`
- UI should show friendly labels like `Sunday (T-1)`
- a route option may contain multiple airports and airlines
- each route option is capped at 3 origin airports and 3 destination airports
- nonstop is implicit in v0

### Trip Instance

Generated dated occurrence.

Key fields:

- `trip_instance_id`
- `trip_id`
- `anchor_date`
- `display_label`
- `travel_state`
- `recommendation_state`
- `booking_id`

### Tracker

Operational tracker row per route option per trip instance.

Key fields:

- `tracker_id`
- `trip_instance_id`
- `route_option_id`
- `travel_date`
- `tracking_status`
- tracker-level signal fields such as latest price, latest winning airport pair, and latest signal source

Trackers are the planning and recommendation unit. They are not the concrete fetch unit.

### Tracker Fetch Target

Concrete airport-pair Google Flights search row under a tracker.

Key fields:

- `fetch_target_id`
- `tracker_id`
- `trip_instance_id`
- `origin_airport`
- `destination_airport`
- `google_flights_url`
- `last_fetch_status`
- `next_fetch_not_before`
- `schedule_offset_seconds`
  Shared across all fetch targets in the same trip and derived from the trip creation time.
- latest fetched price and summary fields

Each tracker can fan out to at most 9 fetch targets.

### Price Record

Append-only historical fact row produced by a successful fetch target request.

Key fields:

- `price_record_id`
- `fetch_event_id`
- `observed_at`
- `observed_date`
- `provider`
- `fetch_method`
- `fetch_target_id`
- `tracker_id`
- `trip_instance_id`
- `trip_id`
- `route_option_id`
- `tracker_definition_signature`
- search-envelope snapshot fields
- concrete airport-pair query fields
- parsed offer fields such as airline, departure label, arrival label, and price
- `offer_rank`
- `request_offer_count`
- `is_request_cheapest`
- `record_signature`

Notes:

- one successful fetch can create many price records
- the table is append-only
- current tracker state is still derived separately from the latest fetch-target rollups
- tracker edits can invalidate current price state without deleting old historical records

### Booking

Attached booking linked to a trip instance and, ideally, to a tracker.

### Unmatched Booking

Booking that needs user resolution.

This is the only user-facing resolution queue in the MVP.

## Core Flows

### 1. Trip Creation

1. User creates a trip.
2. User selects `one_time` or `weekly`.
3. User adds ranked route options.
4. App validates uniqueness and route-option limits.
5. App saves trips and route options.
6. App generates trip instances.
7. App generates one tracker per route option per trip instance.
8. App generates one fetch target per tracker + airport pair.

### 2. Weekly Reconciliation

Whenever trips are regenerated:

- keep the next 12 future weekly instances
- preserve existing matching instances when possible
- add the newly in-scope 12th week
- do not recreate skipped or booked occurrences blindly

Generation must be idempotent.

### 3. Tracker Setup and Coverage

1. App shows one tracker row per route option per trip instance.
2. Each tracker shows one short Google Flights link per airport pair.
3. Background fetch is enabled automatically for every tracker.
4. The worker queries a small number of fetch targets serially.
5. The cheapest successful fetch target rolls back onto the tracker as the best known price.
6. Every successful fetch target request also appends one row per parsed offer into `price_records.csv`.

### 4. Booking Intake

1. User records a booking.
2. App attempts to match it to an existing trip instance and tracker.
3. If the match is confident, create a `Booking`.
4. If the match is not confident, create an `UnmatchedBooking`.
5. Resolve only unmatched bookings, never tracker noise.

## Background Fetch Rules

- never fetch in a request path
- fetch only from a separate worker CLI
- in local use, macOS `launchd` is the preferred scheduler for repeatedly invoking that CLI
- fetch serially, not in parallel
- refresh each concrete airport-pair target every 4 hours
- use trip-anchored 4-hour refresh windows; the worker itself remains serial and conservative
- apply short sleeps between requests within a worker run
- cap a run at a small batch size
- allow at most one fetch target per tracker per run
- back off after failures
- keep old tracker prices if a new fetch fails
- if a tracker definition changes, invalidate impacted price state and let the next scheduled refresh repopulate it

Suggested worker command:

```bash
uv run python -m app.jobs.fetch_google_flights --max-targets 3
```

## UI Notes

### Trips

- `Recurring trips` remain the parent-management surface
- `Scheduled trips` remain the operational surface
- past instances remain preserved in storage but hidden from the current UI

### Trackers

The Trackers page should feel like an operational coverage view:

- one card per trip instance
- one row per tracker / route option
- rolled-up best price shown on the tracker row
- last updated and next refresh timestamps shown on the tracker row
- short airport-pair links shown under the row
- no manual tracker-link editing surface
