# travel-agent v0 Tech Spec

## Objective

Implement a local-first web app that organizes Google Flights trackers and bookings around named trips.

The app should support:

- one-time trips
- weekly recurring trips
- ranked route options
- rolling 12-week instance generation
- manual Google Flights tracker setup
- manual `.eml` import
- automatic booking attachment when confident
- booking-only resolution flow when not confident

This version intentionally avoids:

- paid fare APIs
- a database
- Gmail polling
- Google Flights scraping
- rich client complexity

## Architecture Summary

v0 consists of five layers:

1. `Web UI`
   FastAPI server-rendered pages for Today, Trips, Bookings, Imports, Resolve, and Trackers.

2. `Domain services`
   Trip planning, recurring-instance generation, tracker synchronization, booking attachment, and recommendation rollup.

3. `Ingestion`
   Google Flights email parsing and safe observation matching.

4. `Storage`
   CSV and JSON files under `data/`.

5. `Upstream signal source`
   Official Google Flights tracking configured manually by the user.

## Stack

- Python 3.12+
- `uv`
- FastAPI
- Jinja2 templates
- small htmx enhancements where useful
- Pydantic models
- standard-library CSV, JSON, and `email` modules

## Why This Stack

- local file storage is enough for a single-user MVP
- the product is mostly forms, lists, and derived status
- Python fits recurring generation, parsing, and recommendation logic well
- server-rendered pages keep the implementation small and easy to reason about

## Repository Layout

Target structure:

```text
travel-agent/
  app/
    main.py
    settings.py
    catalog.py
    routes/
      today.py
      trips.py
      bookings.py
      imports.py
      resolve.py
      trackers.py
    services/
      trips.py
      trip_instances.py
      trackers.py
      bookings.py
      imports.py
      recommendations.py
      projections.py
    ingestion/
      google_flights_email_parser.py
      observation_matcher.py
    storage/
      csv_store.py
      json_store.py
      repository.py
      uploaded_email_store.py
    models/
      app_state.py
      trip.py
      route_option.py
      trip_instance.py
      tracker.py
      booking.py
      unmatched_booking.py
      email_event.py
      fare_observation.py
      view_models.py
    templates/
      layout.html
      today.html
      trips.html
      trip_detail.html
      bookings.html
      booking_form.html
      imports.html
      resolve.html
      trackers.html
      partials/
    static/
      app.css
      trips.js
  data/
    imported_emails/
  planning/
  tests/
```

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

- `day_offset` is stored as an integer
- UI should show friendly labels like `Sunday (T-1)`
- a route option may contain multiple airports and airlines
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
- `google_flights_url`
- `tracking_status`
- latest signal projection fields

### Booking

Attached booking.

### Unmatched Booking

Booking that needs user resolution.

This is the only user-facing resolution queue in the MVP.

## Core Flows

### 1. Trip Creation

1. User creates a trip.
2. User selects `one_time` or `weekly`.
3. User adds ranked route options.
4. App validates uniqueness and route option completeness.
5. App saves trips and route options.
6. App generates trip instances.
7. App generates trackers.

### 2. Weekly Reconciliation

Whenever trips are regenerated:

- keep the next 12 future weekly instances
- preserve existing matching instances when possible
- add the newly in-scope 12th week
- do not recreate skipped or booked occurrences blindly

Generation must be idempotent.

### 3. Tracker Setup

1. App shows one tracker row per route option per trip instance.
2. User opens the generated Google Flights link or pastes a better one.
3. User enables `Track prices` in Google Flights.
4. User marks the tracker as enabled.

### 4. Email Import

1. User uploads a `.eml`.
2. Raw email is stored under `data/imported_emails/`.
3. Parser extracts candidate observations.
4. Matcher attempts to place observations against trackers.
5. Only confident matches produce `fare_observations`.
6. Unmatched tracker observations are ignored.
7. Tracker and trip projections are recomputed.

### 5. Booking Intake

1. User records a booking.
2. App attempts to match it to an existing trip instance and tracker.
3. If the match is confident, create a `Booking`.
4. If not, create an `UnmatchedBooking`.
5. `Resolve` lets the user link the unmatched booking to an existing trip instance or create a new one-time trip.

### 6. Recommendation Refresh

1. Read trips, route options, instances, trackers, bookings, and observations.
2. Compute tracker projections.
3. Roll the best accepted observation into trip-instance status.
4. Derive:
   - `needs_tracker_setup`
   - `wait`
   - `book_now`
   - `booked_monitoring`
   - `rebook`

For v0, a booked trip instance becomes `rebook` only when the latest matched observation is strictly cheaper than the booked price.

## Routes

### Pages

- `GET /`
  Today dashboard.

- `GET /trips`
  Trips-first workspace with recurring cards, scheduled-trip filters, and links into creation/editing.

- `GET /trips/{trip_id}`
  Backward-compatible redirect into the filtered Trips workspace.

- `GET /bookings`
  Booking list and add-booking entry point.

- `GET /imports`
  Manual `.eml` import and recent import history.

- `GET /resolve`
  Unmatched booking resolution only.

- `GET /trackers`
  Operational tracker management.

### Actions

- `POST /trips`
  Create or update a trip and regenerate dependent instances and trackers.

- `POST /trips/{trip_id}/pause`
  Pause a recurring trip.

- `POST /trips/{trip_id}/delete`
  Delete a trip and dependent future operational rows.

- `POST /trip-instances/{trip_instance_id}/skip`
  Skip one occurrence.

- `POST /trip-instances/{trip_instance_id}/restore`
  Restore one skipped occurrence.

- `POST /trackers/{tracker_id}/mark-enabled`
  Mark tracker enabled.

- `POST /trackers/{tracker_id}/paste-link`
  Save a manual Google Flights URL.

- `POST /bookings`
  Create a booking or unmatched booking.

- `POST /imports/email`
  Import one `.eml` file.

- `POST /resolve/{unmatched_booking_id}/link`
  Link unmatched booking to an existing trip instance.

- `POST /resolve/{unmatched_booking_id}/create-trip`
  Create a new one-time trip from an unmatched booking.

## Storage and Repository Boundaries

The repository layer should expose first-class operations for:

- `load_trips` / `save_trips`
- `load_route_options` / `save_route_options`
- `load_trip_instances` / `save_trip_instances`
- `load_trackers` / `save_trackers`
- `load_bookings` / `save_bookings`
- `load_unmatched_bookings` / `save_unmatched_bookings`
- `load_email_events` / `save_email_events`
- `load_fare_observations` / `save_fare_observations`

Repository bootstrap should create empty CSV files for the new schema automatically.

Backward compatibility with the earlier rules-first CSV layout is not required. The existing test data can be discarded.

## Matching Policy

### Tracker observations

- confident match -> accept and store
- ambiguous match -> ignore
- no match -> ignore

These should not create user-facing resolve work.

### Bookings

- confident match -> attach automatically
- ambiguous match -> unmatched booking
- no match -> unmatched booking

Only bookings should create user-facing resolution work.

## Frontend Guidelines

- Trips-first information architecture
- searchable multi-select chips for airports and airlines
- friendly day selector derived from anchor day, such as `Sunday (T-1)`
- route options are ordered and re-rankable
- recurring management controls live on the Trips workspace instead of a dedicated detail page
- operational tracker detail is accessible but not the dominant UX

## Testing Strategy

Cover at minimum:

- unique trip-label validation
- route-option validation
- one-time trip generation
- weekly rolling 12-week generation
- tracker creation from route options
- skip and restore behavior
- booking auto-match
- unmatched booking creation
- resolve flow behavior
- Google Flights email parsing
- observation matcher ignoring ambiguous tracker signals
- booked vs latest observation recommendation logic
