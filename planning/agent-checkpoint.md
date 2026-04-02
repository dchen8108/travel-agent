# Agent Checkpoint

Last refreshed: `2026-04-01`

## Purpose

This is the fast bootstrap doc for a fresh agent that needs the current repo state, not the historical plan.

## Product Snapshot

`travel-agent` is now a local-first recurring flight control panel for one user.

Current product shape:

- `Trip` is the authored planning object
- trips are `one_time` or `weekly`
- weekly trips generate rolling dated `TripInstance` rows
- `RouteOption` rows are ranked tracker definitions under a trip
- each `Tracker` materializes one route option for one trip instance
- each tracker fans out into concrete airport-pair `TrackerFetchTarget` rows
- Google Flights prices are fetched by a conservative in-house background worker
- `Booking` rows are trip-scoped, not tracker-scoped
- unresolved bookings are handled inline on `Bookings`
- Gmail booking automation can auto-create bookings and auto-cancel existing ones

There is no primary top-level `Resolve` workspace anymore. The `Bookings` page is the booking management surface, including unmatched items.

## Current UX Model

Primary screens:

- `Today`
- `Trips`
- `Bookings`
- scheduled-trip detail pages at `/trip-instances/{trip_instance_id}`

Important hierarchy:

- weekly trips still have a parent plan page
- one-time trips use their scheduled-trip page as the canonical page
- scheduled trips are the operational surface where you inspect prices, refresh, skip, book, unlink, and archive

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

Frontend JS is now split by page/concern:

- `app/static/app.js`
- `app/static/pickers.js`
- `app/static/trip_form.js`
- `app/static/booking_form.js`
- `app/static/scheduled_filters.js`

The old monolithic `app/static/trips.js` has been removed.

## Background Jobs

### Google Flights Fetcher

- entrypoint: `app/jobs/fetch_google_flights.py`
- serial, conservative worker
- 4-hour trip-anchored cadence
- launchd default: every `60s`, max `2` targets per run

### Gmail Booking Poller

- entrypoint: `app/jobs/poll_gmail_bookings.py`
- launchd default: every `180s`, max `10` messages per run
- first does one inbox backfill, then switches to Gmail History API incremental sync
- dedupes by `booking_email_events.gmail_message_id`
- only retryable `error` events are retried, bounded by `max_retry_attempts`
- per-message failures no longer abort the whole poll batch
- OpenAI extraction model I/O is redacted from logs by default unless `debug_log_model_io` is enabled in `config/gmail_integration.json`

Launchd secret handling:

- `install_launchd_booking_poller` will persist `OPENAI_API_KEY` into `config/local/openai_api_key.txt` if needed, so the poller does not depend on shell startup files

## Key Domain Semantics

`Trip`

- top-level planning object
- unique label
- `one_time` or `weekly`
- `preference_mode` is `equal` or `ranked_bias`

`RouteOption`

- ranked tracker definition under a trip
- can include multiple origin airports, destination airports, and airlines
- includes fare policy:
  - `include_basic`
  - `exclude_basic`

`TripInstance`

- one dated operational trip
- `travel_state` is the main lifecycle field

`Tracker`

- one route option instantiated for one trip instance
- stores rolled-up best current price signal

`TrackerFetchTarget`

- one concrete airport-pair Google Flights query
- this is the real polling queue row

`Booking`

- belongs to a trip instance
- multiple bookings per trip instance are allowed
- one booking can belong to at most one trip instance
- booked-vs-current comparison is trip-level, not tracker-pinned

`UnmatchedBooking`

- unresolved booking record surfaced inline on `Bookings`
- still backed by the shared `bookings` SQLite table under `match_status = 'unmatched'`

`BookingEmailEvent`

- one Gmail intake audit row
- records ignored, duplicate, auto-resolved, needs-resolution, and error outcomes

`PriceRecord`

- append-only fetched-offer history
- one successful fetch can create multiple rows

## Important Product Decisions

- booking comparison uses the best current trip option after preferences/bias are applied
- one-time trip deletion is a tombstone/archive, not a hard delete
- active bookings block one-time trip archive
- test data is explicit via `data_scope = live | test`
- UI visibility and operational processing of test data are separately configurable through:
  - `show_test_data`
  - `process_test_data`

## Verified State

Verified on this machine during the latest cleanup pass:

- `uv run pytest -q` -> `112 passed`
- `uv run python -m compileall app tests` -> clean
- Playwright smoke passed for:
  - `/trips`
  - `/trips/new`
  - `/bookings`
  - `/bookings/new`

## Read These First

High signal files:

- [README.md](/Users/davidchen/code/travel-agent/README.md)
- [planning/README.md](/Users/davidchen/code/travel-agent/planning/README.md)
- [planning/sqlite-storage.md](/Users/davidchen/code/travel-agent/planning/sqlite-storage.md)
- [planning/gmail-booking-ingestion.md](/Users/davidchen/code/travel-agent/planning/gmail-booking-ingestion.md)

Entrypoints:

- [app/main.py](/Users/davidchen/code/travel-agent/app/main.py)
- [app/settings.py](/Users/davidchen/code/travel-agent/app/settings.py)
- [app/web.py](/Users/davidchen/code/travel-agent/app/web.py)

Core routes:

- [app/routes/today.py](/Users/davidchen/code/travel-agent/app/routes/today.py)
- [app/routes/trips.py](/Users/davidchen/code/travel-agent/app/routes/trips.py)
- [app/routes/trackers.py](/Users/davidchen/code/travel-agent/app/routes/trackers.py)
- [app/routes/bookings.py](/Users/davidchen/code/travel-agent/app/routes/bookings.py)

Core services:

- [app/services/workflows.py](/Users/davidchen/code/travel-agent/app/services/workflows.py)
- [app/services/dashboard.py](/Users/davidchen/code/travel-agent/app/services/dashboard.py)
- [app/services/trips.py](/Users/davidchen/code/travel-agent/app/services/trips.py)
- [app/services/bookings.py](/Users/davidchen/code/travel-agent/app/services/bookings.py)
- [app/services/background_fetch.py](/Users/davidchen/code/travel-agent/app/services/background_fetch.py)
- [app/services/google_flights_fetcher.py](/Users/davidchen/code/travel-agent/app/services/google_flights_fetcher.py)
- [app/services/booking_email_ingest.py](/Users/davidchen/code/travel-agent/app/services/booking_email_ingest.py)
- [app/services/booking_extraction.py](/Users/davidchen/code/travel-agent/app/services/booking_extraction.py)

Persistence:

- [app/storage/repository.py](/Users/davidchen/code/travel-agent/app/storage/repository.py)
- [app/storage/sqlite_store.py](/Users/davidchen/code/travel-agent/app/storage/sqlite_store.py)
- [app/storage/sqlite_schema.py](/Users/davidchen/code/travel-agent/app/storage/sqlite_schema.py)

Frontend:

- [app/templates/trips.html](/Users/davidchen/code/travel-agent/app/templates/trips.html)
- [app/templates/trip_form.html](/Users/davidchen/code/travel-agent/app/templates/trip_form.html)
- [app/templates/booking_form.html](/Users/davidchen/code/travel-agent/app/templates/booking_form.html)
- [app/templates/trip_instance_detail.html](/Users/davidchen/code/travel-agent/app/templates/trip_instance_detail.html)
- [app/static/app.css](/Users/davidchen/code/travel-agent/app/static/app.css)
- [app/static/pickers.js](/Users/davidchen/code/travel-agent/app/static/pickers.js)

## Current Caution Areas

- `dashboard.py` still owns a lot of derived UI logic and is a natural future decomposition candidate
- `sync_and_persist(...)` still rewrites several reconciled tables as full snapshots; high-churn booking/event paths are safer now, but broader row-level persistence cleanup could go further
- Google Flights parsing remains heuristic and should be treated as drift-prone external HTML parsing
