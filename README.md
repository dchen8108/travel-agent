# travel-agent

Local-first tracker-of-trackers for recurring flight travel.

This MVP is built around a simple idea:

- you organize travel into named `Trips`
- each trip owns one or more ranked `Route Options`
- each route option corresponds to one Google Flights tracker/search definition, including whether Basic economy should be included or excluded
- trips can treat route options equally or require lower-ranked options to clear user-defined savings thresholds
- the app generates dated `Trip Instances` and per-instance `Trackers`
- the app fans each tracker out into concrete airport-pair Google Flights searches
- a background job queries those links conservatively every 4 hours on trip-anchored refresh windows and rolls the best current price back onto the tracker
- saving a trip pulls its affected airport-pair searches to the front of the refresh queue
- the app stores tracker signals, organizes bookings, and tells you what still needs attention

This version is intentionally local and simple:

- one user
- local CSV/JSON storage under `data/`
- one-time or weekly trips
- a rolling 12-week horizon for weekly trips
- in-house Google Flights background fetching
- automatic background tracking enabled by default for every tracker
- at most 3 origin airports and 3 destination airports per route option
- append-only fetched offer history under `data/price_records.csv`
- no paid fare APIs
- no Gmail automation
- no credits or hotels

## Core Objects

- `Trip`: authoring object with a unique label
- `Route Option`: ranked tracker definition under a trip
- `Trip Instance`: one dated scheduled trip, either standalone or generated from a weekly trip
- `Tracker`: one Google Flights tracker/search envelope for a route option on a trip instance
- `Tracker Fetch Target`: one concrete airport-pair Google Flights search under a tracker
- `Price Record`: one append-only fetched offer row captured for analytics history
- `Booking`: a purchased itinerary attached to a trip instance
- `Unmatched Booking`: a booking the system could not confidently place

## Run

```bash
uv sync --python 3.12
uv run uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000`.

## MVP Flow

1. Create a `Trip`.
2. Choose whether it is `one_time` or `weekly`.
3. Choose whether route options should be treated equally or in ranked order.
4. Add ranked `Route Options`.
5. For each route option, choose whether Google Flights should include or exclude Basic economy fares.
6. Optionally require lower-ranked options to be cheaper by configured dollar amounts.
7. Use `Trips` to manage recurring plans and browse the dated scheduled trips they create.
8. Open a recurring trip for parent-level details, route options, and scheduled dates.
9. Open any scheduled trip to review its trackers, prices, airport-pair Google Flights links, fare-policy labels, and booking state.
10. Let the background fetcher populate current prices automatically. New or edited trips are queued to refresh first.
11. Record bookings in the app.
12. Let the app continue comparing booked prices against tracker prices.

## Tests

```bash
uv run pytest -q
```

## Playwright Smoke Checks

Playwright is installed as a dev dependency for targeted browser debugging, not as part of the default pytest suite.

Quick smoke against a temporary local server:

```bash
uv run python scripts/playwright_smoke.py --serve --path /trips
```

Example filter/screenshot check:

```bash
uv run python scripts/playwright_smoke.py \
  --serve \
  --path /trips \
  --fill '[data-filter-search]=New York' \
  --wait-ms 500 \
  --screenshot /tmp/trips-filtered.png
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

## Historical Price Records

Every successful background Google Flights request now appends rows to `data/price_records.csv`.

Important behavior:

- one fetch target request can create many price records
- each row represents one parsed itinerary/price, not just the cheapest result
- current tracker state still stores only the latest best rollup
- price history is append-only and survives tracker-definition edits
- each row also records whether the originating tracker allowed or excluded Basic economy fares

This gives the app a long-term local fact table for analytics without changing the live tracker UI yet.
