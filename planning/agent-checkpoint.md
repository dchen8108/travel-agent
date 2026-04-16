# Agent Checkpoint

Last refreshed: `2026-04-10`

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
- `Booking` may be linked to a scheduled trip and can optionally link to a uniquely matched route option
- unresolved bookings are still `Booking` rows, not a separate object type

There is no primary `Resolve`, `Trips`, or `Bookings` workspace anymore. The dashboard is the primary control surface, with compatibility redirects and focused create/edit flows branching from it.

## Current UX Model

Primary screens:

- dashboard at `/`
- dashboard modal panels for trip bookings and trackers
- focused create/edit flows such as `/trips/new` and trip-scoped `/bookings/new?trip_instance_id=...`
- compatibility redirects under `/groups/{trip_group_id}`, `/trip-instances/{trip_instance_id}`, and `/trips/{trip_id}`
- the persistent Milemark mark/wordmark is the global route back to `/`; page-level `Back` links are only local navigation helpers

Important hierarchy:

- the dashboard is the canonical operational page
- groups are organizational only and are inspected inline on collection cards
- scheduled trips are inspected inline in the dashboard ledger, with bookings and trackers opening in modal panels
- recurring rules do not keep a standalone detail page; `/trips/{trip_id}` redirects to edit for weekly rules
- `/groups/{id}` and `/trip-instances/{id}` are compatibility redirects, not primary destinations
- unlinked bookings are resolved inline on the dashboard

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
- local secrets, OAuth artifacts, and machine-specific overrides: `config/local/`
- there is no remaining runtime bootstrap from SQLite `app_state`; JSON config is the only live app-config source now

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
- queue-based cadence, with launchd defaults coming from `config/app_state.json`
- fetch-target leases prevent overlapping workers from fetching the same tracker concurrently

### Gmail Booking Poller

- entrypoint: `app/jobs/poll_gmail_bookings.py`
- launchd defaults come from `config/gmail_integration.json`
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
- there is no separate user-facing skip lifecycle; recurring exceptions are represented by deleting attached occurrences or detaching them into standalone one-time trips
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
  - `/trips/new`
  - `/bookings/new?trip_instance_id={id}`
  - `/?panel=bookings&trip_instance_id={id}`
  - `/?panel=trackers&trip_instance_id={id}`
  - `/groups/{id}/edit`
  - `/groups/new`

## Storage Hygiene Notes

- `initialize_schema()` is version-gated; legacy migrations should not mutate a current-schema database on normal startup
- workflow reconciliation is split into `build_reconciled_snapshot()` and `persist_reconciled_snapshot()` in `app/services/workflows.py`; keep pure reconciliation separate from persistence where possible
- dashboard/routes now distinguish explicit persisted reads vs live recompute via `load_persisted_snapshot()` and `load_live_snapshot()` in `app/services/dashboard_snapshot.py`; prefer persisted reads for pure form/render paths
- the old `dashboard.py` and `scheduled_trip_views.py` barrels are gone; shared trip row/state logic now lives in `app/services/scheduled_trip_display.py` and `app/services/scheduled_trip_state.py`, while dashboard-specific snapshot/query/navigation helpers live in the `dashboard_*` modules
- if you touch storage init or migration code, add an explicit regression test in `tests/test_repository.py` that proves the current-schema startup path stays read-only

## Read These First

High-signal docs:

- [README.md](/Users/davidchen/code/travel-agent/README.md)
- [planning/README.md](/Users/davidchen/code/travel-agent/planning/README.md)
- [planning/sqlite-storage.md](/Users/davidchen/code/travel-agent/planning/sqlite-storage.md)
- [planning/gmail-booking-ingestion.md](/Users/davidchen/code/travel-agent/planning/gmail-booking-ingestion.md)
- [planning/trip-groups-and-recurring-rules.md](/Users/davidchen/code/travel-agent/planning/trip-groups-and-recurring-rules.md) for transition context only

Entrypoints:

- [app/main.py](/Users/davidchen/code/travel-agent/app/main.py)
- [app/routes/today.py](/Users/davidchen/code/travel-agent/app/routes/today.py)
- [app/routes/bookings.py](/Users/davidchen/code/travel-agent/app/routes/bookings.py)
- [app/routes/groups.py](/Users/davidchen/code/travel-agent/app/routes/groups.py)
- [app/routes/trackers.py](/Users/davidchen/code/travel-agent/app/routes/trackers.py)

Core services:

- [app/services/dashboard_snapshot.py](/Users/davidchen/code/travel-agent/app/services/dashboard_snapshot.py)
- [app/services/dashboard_queries.py](/Users/davidchen/code/travel-agent/app/services/dashboard_queries.py)
- [app/services/dashboard_booking_views.py](/Users/davidchen/code/travel-agent/app/services/dashboard_booking_views.py)
- [app/services/dashboard_navigation.py](/Users/davidchen/code/travel-agent/app/services/dashboard_navigation.py)
- [app/services/scheduled_trip_state.py](/Users/davidchen/code/travel-agent/app/services/scheduled_trip_state.py)
- [app/services/scheduled_trip_display.py](/Users/davidchen/code/travel-agent/app/services/scheduled_trip_display.py)
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

- `scheduled_trip_state.py` and `scheduled_trip_display.py` are smaller than the old shared barrel, but they are now the main place to watch for future UI/runtime drift in trip-row logic
- `dashboard_queries.py` is still fairly dense because it owns the snapshot-level scheduled/group query helpers
- Google Flights parsing is still heuristic HTML parsing and should be treated as drift-prone
- rule deletion is intentionally deferred because the attached-occurrence lifecycle needs an explicit product decision first
