# Agent Checkpoint

Last refreshed: `2026-04-02`

## Purpose

This is the high-signal bootstrap note for a fresh agent. It should describe the live implementation, not the historical plan.

## Product Snapshot

`travel-agent` is a local-first recurring flight control panel for one user.

Core product shape:

- `Trip Group` organizes related scheduled trips
- `Recurring Rule` generates future scheduled trips into one or more groups
- `Trip` is the authoring object for either a one-time trip or a recurring rule
- `Trip Instance` is the concrete dated trip you actually manage
- `Route Option` is a ranked itinerary definition under a trip
- `Tracker` and `Tracker Fetch Target` are derived monitoring objects
- `Booking` belongs to a scheduled trip and can optionally link to a uniquely matched route option

There is no primary `Resolve` workspace anymore. `Bookings` is the booking-management surface.

## Current UX Model

Primary screens:

- `Today`
- `Trips`
- `Bookings`
- scheduled-trip detail pages at `/trip-instances/{trip_instance_id}`

Important hierarchy:

- one-time trips use their scheduled-trip page as the canonical operational page
- recurring rules still keep a parent rule page
- groups are organizational only
- scheduled trips are the operational surface where you inspect prices, refresh, book, detach, unlink, or delete

## Runtime Architecture

Stack:

- Python `3.12`
- FastAPI
- Jinja templates
- vanilla JS
- local SQLite storage

Runtime storage/config:

- SQLite DB: `data/travel_agent.sqlite3`
- checked-in app config: `config/app_state.json`
- checked-in Gmail config: `config/gmail_integration.json`
- local secrets and OAuth artifacts: `config/local/`

Frontend JS is split by concern:

- `app/static/app.js`
- `app/static/pickers.js`
- `app/static/trip_form.js`
- `app/static/booking_form.js`
- `app/static/scheduled_filters.js`

## Background Jobs

### Google Flights Fetcher

- entrypoint: `app/jobs/fetch_google_flights.py`
- conservative serial worker
- queue-based cadence, with launchd defaulting to every `60s`
- fetch-target leases prevent overlapping workers from fetching the same tracker concurrently

### Gmail Booking Poller

- entrypoint: `app/jobs/poll_gmail_bookings.py`
- launchd default: every `180s`, max `10` messages per run
- one-time backfill, then Gmail History API incremental sync
- dedupe by `booking_email_events.gmail_message_id`
- retries only retryable `error` events, bounded by `max_retry_attempts`
- model I/O is redacted from logs unless `debug_log_model_io` is enabled

## Current Domain Semantics

`Trip`

- unique recurring-rule labels
- one-time labels can repeat across dates
- `active` on the authored trip is only the parent/rule activation tombstone, not the scheduled-trip lifecycle

`Trip Instance`

- one concrete scheduled trip
- no persisted lifecycle enum anymore
- lifecycle is derived:
  - `Planned` if it has no active bookings
  - `Booked` if it has at least one active booking
- deletion is represented by `deleted`

`Booking`

- belongs to exactly one trip instance when linked
- can optionally link to a route option if the match is unique
- route mismatch clears that optional link, but does not unlink the booking from the trip

`Tracker`

- one route option instantiated for one trip instance
- stores rolled-up best current signal from concrete fetch targets

## Important Product Decisions

- booking comparison is trip-level, using the best current route after preference bias
- bookings can optionally link back to the exact tracked route when the match is unique
- there is no user-facing skip state anymore; recurring exceptions are handled by deleting occurrences
- deleting a recurring occurrence suppresses regeneration for that rule/date
- one-time trip deletion is a tombstone, not a hard delete
- recurring rules are required to belong to at least one group in the normal UI
- test data is explicit through `data_scope = live | test`

## Current Verification Baseline

Known-good on this machine after the latest cleanup pass:

- `uv run pytest -q`
- `uv run python -m compileall app tests`
- Playwright/browser smoke on:
  - `/`
  - `/trips`
  - `/bookings`
  - `/groups/{id}`
  - `/trip-instances/{id}`

## Read These First

High-signal docs:

- [README.md](/Users/davidchen/code/travel-agent/README.md)
- [planning/README.md](/Users/davidchen/code/travel-agent/planning/README.md)
- [planning/sqlite-storage.md](/Users/davidchen/code/travel-agent/planning/sqlite-storage.md)
- [planning/gmail-booking-ingestion.md](/Users/davidchen/code/travel-agent/planning/gmail-booking-ingestion.md)
- [planning/trip-groups-and-recurring-rules.md](/Users/davidchen/code/travel-agent/planning/trip-groups-and-recurring-rules.md)

Entrypoints:

- [app/main.py](/Users/davidchen/code/travel-agent/app/main.py)
- [app/routes/today.py](/Users/davidchen/code/travel-agent/app/routes/today.py)
- [app/routes/trips.py](/Users/davidchen/code/travel-agent/app/routes/trips.py)
- [app/routes/bookings.py](/Users/davidchen/code/travel-agent/app/routes/bookings.py)
- [app/routes/groups.py](/Users/davidchen/code/travel-agent/app/routes/groups.py)
- [app/routes/trackers.py](/Users/davidchen/code/travel-agent/app/routes/trackers.py)

Core services:

- [app/services/dashboard.py](/Users/davidchen/code/travel-agent/app/services/dashboard.py)
- [app/services/workflows.py](/Users/davidchen/code/travel-agent/app/services/workflows.py)
- [app/services/trips.py](/Users/davidchen/code/travel-agent/app/services/trips.py)
- [app/services/bookings.py](/Users/davidchen/code/travel-agent/app/services/bookings.py)
- [app/services/group_memberships.py](/Users/davidchen/code/travel-agent/app/services/group_memberships.py)
- [app/services/background_fetch.py](/Users/davidchen/code/travel-agent/app/services/background_fetch.py)

Persistence:

- [app/storage/repository.py](/Users/davidchen/code/travel-agent/app/storage/repository.py)
- [app/storage/sqlite_store.py](/Users/davidchen/code/travel-agent/app/storage/sqlite_store.py)
- [app/storage/sqlite_schema.py](/Users/davidchen/code/travel-agent/app/storage/sqlite_schema.py)

## Current Caution Areas

- `dashboard.py` still owns a lot of derived view logic and remains the best future decomposition candidate
- Google Flights parsing is still heuristic HTML parsing and should be treated as drift-prone
- rule deletion is intentionally deferred because the attached-occurrence lifecycle needs an explicit product decision first
