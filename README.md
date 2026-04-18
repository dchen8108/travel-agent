# travel-agent

Local-first tracker-of-trackers for recurring flight travel.

This MVP is built around a simple idea:

- you organize travel into named `Collections`
- you define recurring trips that generate scheduled travel on a cadence
- each trip owns one or more ranked `Route Options`
- each route option corresponds to one Google Flights tracker/search definition, including the selected fare class
- trips can treat route options equally or require lower-ranked options to clear user-defined savings thresholds
- recurring trips generate dated `Trip Instances` that can stay attached or be detached later
- the app keeps concrete `Trip Instances` and per-instance `Trackers`
- the app fans each tracker out into concrete airport-pair Google Flights searches
- a background job refreshes those links conservatively in stale-first order and rolls the best current price back onto the tracker
- saving a trip requests a faster refresh for its affected airport-pair searches without depending on a user-visible queue
- the app stores tracker signals, organizes bookings, and tells you what still needs attention

This version is intentionally local and simple:

- one user
- local SQLite storage under `data/travel_agent.sqlite3`
- checked-in app config under `config/app_state.json`
- one-time or weekly trips
- a rolling 16-week horizon for weekly trips
- in-house Google Flights background fetching
- automatic background tracking enabled by default for every tracker
- at most 3 origin airports and 3 destination airports per route option
- append-only fetched offer history in the `price_records` SQLite table
- Gmail inbox booking automation with OpenAI-backed extraction
- first-class `live` vs `test` data scoping in SQLite
- no paid fare APIs
- no credits or hotels

Use [planning/README.md](/Users/davidchen/code/travel-agent/planning/README.md) to distinguish current design notes from older historical planning docs.

Compatibility note:

- the dashboard at `/` is the primary operational surface
- collections are inspected and edited inline on dashboard collection cards
- trip inspection happens inline on dashboard trip rows and the bookings/trackers modal panels
- trips keep dedicated create/edit pages
- a limited set of old routes still exist as compatibility redirects into the SPA; new work should target `/`, `/trips/new`, `/trips/{id}/edit`, and the `/api/...` endpoints directly

## Core Objects

- `Collection`: pure organization/display for concrete trips
- `Recurring Trip`: cadence + route template that generates future trips into one or more collections
- `Trip`: the authoring object for a one-time trip or a recurring trip
- `Route Option`: ranked tracker definition under a trip
- `Trip Instance`: one dated scheduled trip, either standalone, attached to a recurring rule, or detached from it
- `Tracker`: one Google Flights tracker/search envelope for a route option on a trip instance
- `Tracker Fetch Target`: one concrete airport-pair Google Flights search under a tracker
- `Price Record`: one append-only fetched offer row captured for analytics history
- `Booking`: a purchased itinerary that may be linked to a trip instance and, when uniquely matchable, to one tracked route option
- `Booking Email Event`: one Gmail intake result, including ignored, auto-linked, duplicate, and needs-resolution outcomes

## Run

```bash
uv sync --python 3.12
uv run uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000`.

Frontend stack:

- the React/Vite dashboard is now the primary app at `/`
- trip create/edit now also render through the SPA shell at `/trips/new` and `/trips/{id}/edit`
- there is no mounted server-rendered Jinja UI surface anymore; FastAPI serves the SPA shell, JSON APIs, and compatibility redirects

To work on the frontend locally:

```bash
cd frontend
npm install
npm run dev
```

That starts the Vite dev server and proxies API requests back to the FastAPI app. For a production-style local build, run:

```bash
npm --prefix frontend run build
uv run uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000`.

## MVP Flow

1. Create a `Collection` if you want an organizational bucket.
2. Create a one-time trip or a recurring trip-backed trip.
3. Choose whether route options should be treated equally or in ranked order.
4. Add ranked `Route Options`.
5. For each route option, choose the fare class to track.
6. Optionally require lower-ranked options to be cheaper by configured dollar amounts.
7. Use the dashboard to review collections, recurring trips, upcoming travel, and any bookings that still need linking.
8. Use collection cards to inspect recurring trips and jump straight into recurring-trip edits.
9. Use trip rows and their bookings/trackers modals to inspect bookings, live fares, and Google Flights links.
10. Let the background fetcher populate current prices automatically. New or edited trips are nudged to refresh sooner.
11. Record bookings manually or let Gmail automation create them automatically.
12. Use edit forms for template-level changes, and detach an attached recurring instance before editing it as a one-off trip.

## Gmail Booking Automation

Milemark can poll a dedicated Gmail inbox, classify each new message once, and update bookings automatically when the email can be matched confidently.

Setup:

1. Put your Google desktop OAuth client JSON at:
   - `config/local/gmail_oauth_client.json`
2. Store your OpenAI API key locally:
   - environment variable `OPENAI_API_KEY`, or
   - `config/local/openai_api_key.txt`
3. Run the one-time Gmail auth flow:

```bash
uv run python -m app.jobs.authorize_gmail_bookings
```

4. Install the Gmail poller launchd job:

```bash
uv run python -m app.jobs.install_launchd_booking_poller
```

If `OPENAI_API_KEY` is present in your shell when you run the installer, the installer will persist it to `config/local/openai_api_key.txt` so the launchd job can use it without relying on shell startup files. Re-running the installer with a different `OPENAI_API_KEY` refreshes that cached value.

The installer uses the checked-in defaults from `config/gmail_integration.json` unless you override them on the CLI.
Machine-specific Gmail policy such as sender allowlists can also live in `config/local/gmail_integration.json`, which is merged on top of the checked-in defaults and should not be checked in.

How it behaves:

- polls the inbox directly; no Gmail labels are required
- can hard-gate processing to a sender allowlist via `allowed_from_addresses`; use `config/local/gmail_integration.json` for machine-specific sender filters so checked-in defaults stay generic
- backfills unseen inbox mail once, then switches to Gmail history sync so already-processed messages are not sent back through the LLM
- quickly ignores obvious spam/newsletter messages with a cheap keyword gate
- sends likely booking confirmations to an OpenAI extraction model
- validates and matches extracted legs to existing trip instances
- creates `Booking` rows automatically only when there is exactly one confident trip-instance match
- marks existing bookings `cancelled` automatically when a cancellation email matches cleanly
- creates unlinked `Booking` rows only when a real booking cannot be placed confidently
- records every processed message in `booking_email_events`
- retries only retryable email-processing failures, with a bounded retry count
- redacts model input/output from logs by default unless `debug_log_model_io` is enabled in `config/gmail_integration.json`

The Gmail poller has two separate caps by design:

- `launchd_poll_interval_seconds` / `launchd_max_messages` in `config/gmail_integration.json` control how often launchd starts the poller and the installer default for each run
- `max_messages_per_poll` in `config/gmail_integration.json` is the runtime worker cap inside the poller itself

The effective poll volume is the lower of those two message caps unless you override the CLI on a manual run.

Useful commands:

```bash
uv run python -m app.jobs.poll_gmail_bookings --max-messages 10
uv run python -m app.jobs.uninstall_launchd_booking_poller
```

## Tests

```bash
uv run pytest -q
```

## Playwright Smoke Checks

Playwright is installed as a dev dependency for targeted browser debugging, not as part of the default pytest suite.

Quick smoke against a temporary local server:

```bash
uv run python scripts/playwright_smoke.py --serve --path /
```

Example deep-link screenshot check:

```bash
uv run python scripts/playwright_smoke.py \
  --serve \
  --path '/?panel=bookings&trip_instance_id=inst_23a712a468b6' \
  --wait-for '#root' \
  --screenshot /tmp/dashboard-bookings.png
```

Use `--base-url http://127.0.0.1:8000` instead of `--serve` if the app is already running.

## Background Fetch

Run a conservative Google Flights batch:

```bash
uv run python -m app.jobs.fetch_google_flights --max-targets 3
```

By default, each batch also adds a small random startup delay before it makes any Google Flights request.

Useful for quick testing:

```bash
uv run python -m app.jobs.fetch_google_flights --max-targets 1 --no-sleep --startup-jitter-seconds 0
```

### macOS launchd setup

To make background refreshes automatic on this Mac, install the bundled `launchd` agent:

```bash
uv run python -m app.jobs.install_launchd_fetcher
```

That installs a LaunchAgent that:

- runs at login and then on the checked-in interval in `config/app_state.json`
- fetches up to the configured per-run target cap from `config/app_state.json`
- continuously refreshes the stalest active airport-pair searches first
- adds a small random startup delay before each Google Flights request batch
- keeps a small random delay between requests inside a multi-target batch
- writes structured JSON-line logs under `data/logs/`

The fetcher logs:

- one `run_started` event with stale backlog metadata and selected target ids
- one `target_processed` event per attempted airport-pair fetch with timings, travel metadata, price, and any fetch error
- one `run_completed` or `run_failed` event per batch, including full traceback details on failures

To remove it later:

```bash
uv run python -m app.jobs.uninstall_launchd_fetcher
```

## Config Files

- `config/app_state.json`: checked-in app/runtime policy such as timezone, horizon length, dashboard action windows, fetch cadence/backoff, and launchd fetcher defaults
- `config/gmail_integration.json`: checked-in Gmail poller behavior such as inbox labels, model choice, retry caps, and launchd poller defaults
- `config/local/*`: machine-local secrets and state such as Gmail OAuth credentials, Gmail sync checkpoint, and optional OpenAI API key cache. These files are not product config and should not be checked in.

`config/app_state.json` now acts as the policy surface for both:

- runtime fetcher behavior (stale-first selection, backoff, lease, freshness window, per-run target cap)
- launchd installer defaults (`launchd_fetch_interval_seconds`, `launchd_fetch_max_targets`)

That means the launch cadence and the runtime worker budget are related but distinct; changing one without the other may change when runs start without changing how many searches each run is allowed to refresh.

## Storage

The app stores relational runtime data in `data/travel_agent.sqlite3`.

The `data/` directory is still required at runtime because it holds:

- the live SQLite database
- launchd/background fetch logs under `data/logs/`

App-level config now lives outside the database in:

- [config/app_state.json](/Users/davidchen/code/travel-agent/config/app_state.json)

There is no longer any runtime fallback that migrates app config out of SQLite on startup. If `config/app_state.json` is missing, the app creates a fresh default config file there.

UI/service reads now distinguish between:

- persisted snapshot reads via `load_persisted_snapshot()`
- live recompute-and-persist reads via `load_live_snapshot()`

Pure form/render paths should prefer persisted reads unless they explicitly need fresh reconciliation.

That file is the source of truth for:

- `timezone`
- `future_weeks`
- `enable_background_fetcher`
- dashboard attention windows
- fare freshness window
- background fetch cadence, jitter, backoff, and lease defaults
- launchd fetcher defaults
- `show_test_data`
- `process_test_data`
- config schema `version`

Runtime behavior:

- every main domain row carries `data_scope = 'live' | 'test'`
- the UI hides `test` rows by default
- background fetch, Gmail booking matching, and stale-first refresh selection ignore `test` rows by default
- obvious QA/E2E artifacts are backfilled to `test` during migration

The main logical tables are:

- `trip_groups`
- `trips`
- `rule_group_targets`
- `route_options`
- `trip_instances`
- `trip_instance_group_memberships`
- `trackers`
- `tracker_fetch_targets`
- `bookings`
- `booking_email_events`
- `price_records`

There is still a narrow unresolved-booking view in the product, but it is backed by rows in `bookings` rather than a separate database.

For a more detailed schema map, see [planning/sqlite-storage.md](/Users/davidchen/code/travel-agent/planning/sqlite-storage.md).

## Historical Price Records

Every successful background Google Flights request now appends rows to the `price_records` table in SQLite.

Important behavior:

- one fetch target request can create many price records
- each row represents one parsed itinerary/price, not just the cheapest result
- current tracker state still stores only the latest best rollup
- price history is append-only and survives tracker-definition edits
- each row also records the originating tracker fare class

This gives the app a long-term local fact table for analytics without changing the live tracker UI yet.
