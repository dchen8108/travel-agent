# travel-agent

Local-first tracker-of-trackers for recurring flight travel.

This MVP is built around a simple idea:

- you organize travel into named `Trip Groups`
- you define recurring `Rules` that generate trips on a cadence
- each trip owns one or more ranked `Route Options`
- each route option corresponds to one Google Flights tracker/search definition, including whether Basic economy should be included or excluded
- trips can treat route options equally or require lower-ranked options to clear user-defined savings thresholds
- recurring rules generate dated `Trip Instances` that can stay attached or be detached later
- the app keeps concrete `Trip Instances` and per-instance `Trackers`
- the app fans each tracker out into concrete airport-pair Google Flights searches
- a background job queries those links conservatively on a queued cadence and rolls the best current price back onto the tracker
- saving a trip pulls its affected airport-pair searches to the front of the refresh queue
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

## Core Objects

- `Trip Group`: pure organization/display for concrete trips
- `Recurring Rule`: cadence + route template that generates future trips into one or more groups
- `Trip`: the authoring object for a one-time trip or a recurring rule
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

## MVP Flow

1. Create a `Trip Group` if you want an organizational bucket.
2. Create a one-time trip or a recurring rule-backed trip.
3. Choose whether route options should be treated equally or in ranked order.
4. Add ranked `Route Options`.
5. For each route option, choose whether Google Flights should include or exclude Basic economy fares.
6. Optionally require lower-ranked options to be cheaper by configured dollar amounts.
7. Use the dashboard to review collections, upcoming travel, and any bookings that still need linking.
8. Open a recurring rule for template-level details, route options, and generated dates.
9. Open any scheduled trip to review trackers, prices, Google Flights links, group memberships, and booking state.
10. Let the background fetcher populate current prices automatically. New or edited trips are queued to refresh first.
11. Record bookings manually or let Gmail automation create them automatically.
12. Use the scheduled-trip page as the canonical place to manage linked and cancelled bookings.

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

If `OPENAI_API_KEY` is present in your shell when you run the installer, the installer will persist it to `config/local/openai_api_key.txt` so the launchd job can use it without relying on shell startup files.

How it behaves:

- polls the inbox directly; no Gmail labels are required
- backfills unseen inbox mail once, then switches to Gmail history sync so already-processed messages are not sent back through the LLM
- quickly ignores obvious spam/newsletter messages with a cheap keyword gate
- sends likely booking confirmations to an OpenAI extraction model
- validates and matches extracted legs to existing trip instances
- creates `Booking` rows automatically only when there is exactly one confident trip-instance match
- marks existing bookings `cancelled` automatically when a cancellation email matches cleanly
- creates `Unmatched Booking` rows only when a real booking cannot be placed confidently
- records every processed message in `booking_email_events`
- retries only retryable email-processing failures, with a bounded retry count
- redacts model input/output from logs by default unless `debug_log_model_io` is enabled in `config/gmail_integration.json`

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

Example filter/screenshot check:

```bash
uv run python scripts/playwright_smoke.py \
  --serve \
  --path / \
  --fill '[data-filter-search]=New York' \
  --wait-ms 500 \
  --screenshot /tmp/dashboard-filtered.png
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

- runs at login and every 60 seconds after that
- fetches at most 2 due airport-pair targets per run
- relies on the app's own persisted queue and 4-hour cadence
- adds a small random startup delay before each Google Flights request batch
- keeps a small random delay between requests inside a multi-target batch
- writes structured JSON-line logs under `data/logs/`

The fetcher logs:

- one `run_started` event with queue metadata, due backlog count, and selected target ids
- one `target_processed` event per attempted airport-pair fetch with timings, travel metadata, price, and next refresh time
- one `run_completed` or `run_failed` event per batch, including full traceback details on failures

To remove it later:

```bash
uv run python -m app.jobs.uninstall_launchd_fetcher
```

## Config Files

- `config/app_state.json`: checked-in runtime config such as timezone, horizon length, and whether test data is shown/processed
- `config/gmail_integration.json`: checked-in Gmail poller behavior such as inbox labels, model choice, retry caps, and debug logging
- `config/local/*`: machine-local secrets and state such as Gmail OAuth credentials, Gmail sync checkpoint, and optional OpenAI API key cache. These files are not product config and should not be checked in.

## Storage

The app stores relational runtime data in `data/travel_agent.sqlite3`.

The `data/` directory is still required at runtime because it holds:

- the live SQLite database
- launchd/background fetch logs under `data/logs/`

App-level config now lives outside the database in:

- [config/app_state.json](/Users/davidchen/code/travel-agent/config/app_state.json)

That file is the source of truth for:

- `timezone`
- `future_weeks`
- `enable_background_fetcher`
- `show_test_data`
- `process_test_data`
- config schema `version`

Runtime behavior:

- every main domain row carries `data_scope = 'live' | 'test'`
- the UI hides `test` rows by default
- background fetch, Gmail booking matching, and refresh queueing ignore `test` rows by default
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
- each row also records whether the originating tracker allowed or excluded Basic economy fares

This gives the app a long-term local fact table for analytics without changing the live tracker UI yet.
