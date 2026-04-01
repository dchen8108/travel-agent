# Agent Checkpoint

## Purpose

This document is a bootstrap snapshot for a new agent that needs to regain full context quickly after thread loss or a tooling reset.

It is intentionally practical:

- what the product is now
- what has changed from the original plan
- what is verified
- where to look in the code
- what is currently dirty
- what to do first before making more changes

Last refreshed: `2026-04-01`

## Product Snapshot

`travel-agent` is now a local-first recurring flight control panel that uses an in-house Google Flights background fetcher.

The current product is no longer centered on manual Google Flights `.eml` ingestion as the main path. That earlier plan existed, but the implemented app is now built around:

- parent `Trips`
- ranked `Route Options`
- dated `Trip Instances`
- per-instance `Trackers`
- per-airport-pair `Tracker Fetch Targets`
- append-only `Price Records`
- `Bookings`
- `Unmatched Bookings`

The app is designed for one personal user and focuses on:

- recurring weekly commute planning
- one-time trip tracking
- conservative background price refreshes
- booking capture
- booked-vs-current monitoring
- a narrow booking-only resolution queue

## Current UX Model

Primary screens:

- `Today`
- `Trips`
- `Bookings`
- `Resolve`
- trip-specific scheduled-trip tracker detail pages at `/trip-instances/{trip_instance_id}`

Important UX split:

- `Trips` has a parent/child hierarchy
- weekly trips are the planning layer
- scheduled trip instances are the dated operational layer
- trackers are accessed from a scheduled trip, not from a top-level tracker workspace

Recent hierarchy refactor result:

- recurring trips remain parent plans
- scheduled trips are the instances the user books, skips, refreshes, and monitors

## Architecture Snapshot

Runtime stack:

- Python `3.12`
- `uv`
- FastAPI
- Jinja templates
- vanilla JS
- local CSV/JSON storage under `data/`

Background fetching:

- fetcher job: `app/jobs/fetch_google_flights.py`
- worker is serial and conservative
- fetch targets refresh on a 4-hour cadence
- fetches are staggered and jittered
- one run selects at most one target per tracker and at most `MAX_FETCH_TARGETS_PER_RUN`
- the installed macOS launchd agent currently runs every 60 seconds with `max_targets=2`

Persistence:

- CSV writes are atomic via temp file + rename
- file locking exists in `app/storage/file_lock.py`
- repository layer is `app/storage/repository.py`

## Key Domain Objects

`Trip`

- top-level authored object
- unique label
- `one_time` or `weekly`
- optional `preference_mode`:
  - `equal`
  - `ranked_bias`

`RouteOption`

- ranked search definition under a trip
- can include multiple origin airports, destination airports, and airlines
- has one day offset and one departure window
- carries a fare-class policy:
  - `include_basic`
  - `exclude_basic`
- lower-ranked options can require savings thresholds when preference mode is `ranked_bias`

`TripInstance`

- one dated occurrence
- one-time trips create one standalone instance
- weekly trips generate the next 12 future instances
- past instances are preserved
- the UI now treats `travel_state` as the primary scheduled-trip lifecycle state

`Tracker`

- one per route option per trip instance
- represents a search envelope
- inherits the route option fare-class policy
- stores rolled-up best current signal

`TrackerFetchTarget`

- one concrete airport-pair Google Flights query under a tracker
- this is the actual background polling unit

`PriceRecord`

- append-only historical fetched-offer record
- one successful fetch can append multiple rows
- stores the fare-class policy used to generate the Google Flights query

`Booking`

- attached to a trip instance
- optionally attached to a tracker

`UnmatchedBooking`

- booking resolution queue
- this is the only user-facing resolution queue

## Important Product Decisions

1. The current implementation uses in-house background fetching rather than relying on Google Flights email alerts.
2. Tracker noise is not a resolution queue item.
3. Only unmatched bookings go to `Resolve`.
4. Scheduled trips, not parent trips, are the operational surface.
5. Saving, re-activating, or restoring trips now explicitly queues affected fetch targets to refresh sooner.
6. Targets without a first price are prioritized ahead of steady-state refreshes.
7. Shared route helpers now centralize flash-message redirects and refresh queue orchestration.
8. `Settings` now rejects unknown fields so stale config drift fails fast.
9. The installed launchd fetcher now defaults to `max_targets=2` and keeps between-request jitter.
10. Route options now explicitly choose whether Google Flights should include or exclude Basic economy fares.
11. The UI no longer treats `recommendation_state` as the main source of truth; list and detail views now derive factual copy from bookings, prices, and `travel_state`.

## Important Verified Facts

Verified on this machine:

- repo-local virtualenv exists at `.venv`
- Playwright and Chromium are installed in the repo environment for targeted browser smoke checks
- full test suite currently passes:
  - `/.venv/bin/python -m pytest -q`
  - result at last refresh: `64 passed in 6.14s`
- browser-style in-process sanity pass against live repo data also succeeded via `TestClient`:
  - `/`
  - `/trips`
  - `/bookings`
  - `/resolve`
  - one scheduled-trip detail page under `/trip-instances/{trip_instance_id}`
- `/.venv/bin/python -m compileall app tests` also succeeds
- Playwright smoke harness works:
  - `uv run python scripts/playwright_smoke.py --serve --path /`
  - `uv run python scripts/playwright_smoke.py --serve --path /trips --fill '[data-filter-search]=New York' --wait-ms 600 --screenshot /tmp/travel-agent-trips-filtered.png`

Working tree state at last refresh:

- clean

Recent cleanup/refactor changes implemented:

- shared refresh-queue orchestration across trip and tracker routes
- shared redirect/message helpers across routes
- first-price fetch priority ahead of steady-state refreshes
- trip-edit validation preserving edit context
- a unified snapshot type across dashboard/workflow services
- repository CSV bootstrap/save plumbing reduced to shared helpers
- booking creation/save logic reduced to shared helpers
- stale ignored `imported_email_dir` test settings removed
- dead `app/jobs/import_email_file.py` entrypoint removed
- launchd default fetch batch increased from 1 to 2 while staying serial and jittered

## Key Files To Read First

High-level:

- [README.md](/Users/davidchen/code/travel-agent/README.md)
- [planning/README.md](/Users/davidchen/code/travel-agent/planning/README.md)
- [planning/implementation-plan.md](/Users/davidchen/code/travel-agent/planning/implementation-plan.md)
- [planning/v1-ui-pass.md](/Users/davidchen/code/travel-agent/planning/v1-ui-pass.md)

Entrypoints:

- [app/main.py](/Users/davidchen/code/travel-agent/app/main.py)
- [app/settings.py](/Users/davidchen/code/travel-agent/app/settings.py)
- [app/web.py](/Users/davidchen/code/travel-agent/app/web.py)

Routes:

- [app/routes/today.py](/Users/davidchen/code/travel-agent/app/routes/today.py)
- [app/routes/trips.py](/Users/davidchen/code/travel-agent/app/routes/trips.py)
- [app/routes/trackers.py](/Users/davidchen/code/travel-agent/app/routes/trackers.py)
- [app/routes/bookings.py](/Users/davidchen/code/travel-agent/app/routes/bookings.py)
- [app/routes/resolve.py](/Users/davidchen/code/travel-agent/app/routes/resolve.py)

Core services:

- [app/services/workflows.py](/Users/davidchen/code/travel-agent/app/services/workflows.py)
- [app/services/snapshots.py](/Users/davidchen/code/travel-agent/app/services/snapshots.py)
- [app/services/refresh_queue.py](/Users/davidchen/code/travel-agent/app/services/refresh_queue.py)
- [app/services/trips.py](/Users/davidchen/code/travel-agent/app/services/trips.py)
- [app/services/trip_instances.py](/Users/davidchen/code/travel-agent/app/services/trip_instances.py)
- [app/services/trackers.py](/Users/davidchen/code/travel-agent/app/services/trackers.py)
- [app/services/fetch_targets.py](/Users/davidchen/code/travel-agent/app/services/fetch_targets.py)
- [app/services/background_fetch.py](/Users/davidchen/code/travel-agent/app/services/background_fetch.py)
- [app/services/recommendations.py](/Users/davidchen/code/travel-agent/app/services/recommendations.py)
- [app/services/bookings.py](/Users/davidchen/code/travel-agent/app/services/bookings.py)
- [app/services/dashboard.py](/Users/davidchen/code/travel-agent/app/services/dashboard.py)

Google Flights specifics:

- [app/services/google_flights.py](/Users/davidchen/code/travel-agent/app/services/google_flights.py)
- [app/services/google_flights_fetcher.py](/Users/davidchen/code/travel-agent/app/services/google_flights_fetcher.py)
- [app/services/price_records.py](/Users/davidchen/code/travel-agent/app/services/price_records.py)
- generated Google Flights `tfs` URLs now support a route-option fare policy:
  - `include_basic` remains the default
  - `exclude_basic` is encoded directly into the `tfs` payload
  - no browser automation is required just to switch between those two modes

Persistence:

- [app/storage/repository.py](/Users/davidchen/code/travel-agent/app/storage/repository.py)
- [app/storage/csv_store.py](/Users/davidchen/code/travel-agent/app/storage/csv_store.py)
- [app/storage/file_lock.py](/Users/davidchen/code/travel-agent/app/storage/file_lock.py)

UI:

- [app/templates/trips.html](/Users/davidchen/code/travel-agent/app/templates/trips.html)
- [app/templates/trip_detail.html](/Users/davidchen/code/travel-agent/app/templates/trip_detail.html)
- [app/templates/trip_instance_detail.html](/Users/davidchen/code/travel-agent/app/templates/trip_instance_detail.html)
- [app/templates/today.html](/Users/davidchen/code/travel-agent/app/templates/today.html)
- [app/static/app.css](/Users/davidchen/code/travel-agent/app/static/app.css)
- [app/static/trips.js](/Users/davidchen/code/travel-agent/app/static/trips.js)

Tests:

- [tests/test_trip_workflows.py](/Users/davidchen/code/travel-agent/tests/test_trip_workflows.py)
- [tests/test_background_fetch.py](/Users/davidchen/code/travel-agent/tests/test_background_fetch.py)
- [tests/test_route_preferences.py](/Users/davidchen/code/travel-agent/tests/test_route_preferences.py)
- [tests/test_booking_resolution.py](/Users/davidchen/code/travel-agent/tests/test_booking_resolution.py)
- [tests/test_web_smoke.py](/Users/davidchen/code/travel-agent/tests/test_web_smoke.py)

## Current Known Good Behaviors

- one-time and weekly trips can be created
- weekly trips generate a rolling 12-week horizon
- recurring trips act as parent plans
- scheduled trip instances have dedicated detail pages
- route options can express ranked preference buffers
- route options can independently include or exclude Basic economy fares
- background fetch targets are generated per airport pair
- background fetch parsing can extract offer rows from Google Flights HTML samples
- tracker rollups choose the best fresh fetched target
- bookings can auto-attach when matching is confident
- unmatched bookings go to `Resolve`
- scheduled trips can be skipped and restored
- trip save/activate/restore now queues affected fetch targets for earlier refresh
- no-price fetch targets are prioritized over already-initialized refresh targets
- trip edit validation errors keep the user in edit mode rather than dropping back to a blank create form
- stale settings fields fail fast instead of being silently ignored

## Things To Be Careful About

1. Do not assume the old `.eml`-centric plan is the live implementation path. It is historical planning context, not the current core runtime.
2. The app uses local CSV files with locking, but this is still single-user local software. Be careful with migrations and schema drift.
3. Background fetches are intentionally conservative. Avoid adding eager network fetches to request handlers.
4. The parent trip / scheduled instance split is central to the current UX. Avoid collapsing them back together.
5. The current repo may have uncommitted local changes during active cleanup passes. Do not overwrite them casually.

## Suggested Bootstrap Prompt

Use this when starting a fresh agent:

```text
You are taking over the local project at /Users/davidchen/code/travel-agent.

Before making changes:
1. Read planning/agent-checkpoint.md fully.
2. Read README.md and planning/README.md.
3. Read these implementation files first:
   - app/routes/trips.py
   - app/routes/trackers.py
   - app/services/workflows.py
   - app/services/background_fetch.py
   - app/services/fetch_targets.py
   - app/services/recommendations.py
   - app/services/bookings.py
   - app/services/dashboard.py
4. Read the main UI templates:
   - app/templates/trips.html
   - app/templates/trip_detail.html
   - app/templates/trip_instance_detail.html
   - app/templates/today.html
5. Read the core tests:
   - tests/test_trip_workflows.py
   - tests/test_background_fetch.py
   - tests/test_route_preferences.py
   - tests/test_booking_resolution.py
   - tests/test_web_smoke.py
6. Run `/.venv/bin/python -m pytest -q` from the repo root.
7. Check `git status --short`.

Assume the current product model is:
- recurring parent trips
- scheduled trip instances as operational objects
- background Google Flights fetching via tracker fetch targets
- booking-only resolution queue

When you respond, summarize:
- the architecture as implemented
- any dirty working tree changes
- the last validated test status
- the concrete next step for the user’s current request
```

## Suggested End-Of-Task Refresh Checklist

At the end of meaningful work:

1. update this checkpoint if the architecture, product model, workflows, or runtime instructions changed
2. update README or planning docs if the user-facing behavior changed
3. record the latest test command and result
4. record newly important files or commands
5. note any new risks or known limitations

## Manual QA Checklist

Use this when you want a quick human pass beyond the automated tests.

1. Open `/` and confirm Today renders with summary pills and actionable cards.
2. Open `/trips` and confirm:
   - recurring trips render separately from scheduled trips
   - search/filter UI works
   - skipped trips stay hidden by default
3. Create a one-time trip and confirm the redirect includes a queued-refresh message.
4. Open the created scheduled trip at `/trip-instances/{trip_instance_id}` and confirm:
   - tracker cards render
   - airport-pair link chips render
   - `Next refresh` metadata is visible
5. Create a weekly trip and confirm a rolling future set of scheduled instances appears under the parent trip.
6. Record a booking and confirm it appears on `/bookings`.
7. Record an intentionally unmatched booking and confirm it lands on `/resolve`.
8. Trigger `Refresh sooner` on a scheduled trip and confirm the redirect message reports queued airport-pair searches.
9. If testing with real background fetching, run:
   - `uv run python -m app.jobs.fetch_google_flights --max-targets 1 --no-sleep --startup-jitter-seconds 0`
   Then refresh the scheduled-trip page and confirm a price or a no-results state appears.
