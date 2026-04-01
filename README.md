# travel-agent

Local-first tracker-of-trackers for recurring flight travel.

This MVP is built around a simple idea:

- you organize travel into named `Trips`
- each trip owns one or more ranked `Route Options`
- each route option corresponds to one Google Flights tracker/search definition
- the app generates dated `Trip Instances` and per-instance `Trackers`
- the app fans each tracker out into concrete airport-pair Google Flights searches
- a background job queries those links conservatively and rolls the best current price back onto the tracker
- the app stores tracker signals, organizes bookings, and tells you what still needs attention

This version is intentionally local and simple:

- one user
- local CSV/JSON storage under `data/`
- one-time or weekly trips
- a rolling 12-week horizon for weekly trips
- in-house Google Flights background fetching
- at most 3 origin airports and 3 destination airports per route option
- manual `.eml` upload kept as a legacy fallback
- no paid fare APIs
- no Gmail automation
- no credits or hotels
- a separate `Log past trip` flow for historical travel records

## Core Objects

- `Trip`: authoring object with a unique label
- `Route Option`: ranked tracker definition under a trip
- `Trip Instance`: one dated scheduled trip, either standalone or generated from a weekly trip
- `Tracker`: one Google Flights tracker/search envelope for a route option on a trip instance
- `Tracker Fetch Target`: one concrete airport-pair Google Flights search under a tracker
- `Booking`: a purchased itinerary attached to a trip instance
- `Unmatched Booking`: a booking the system could not confidently place

Past logged trips are still modeled as one-time trips internally, but they intentionally skip route-option and tracker setup. They exist to preserve history and give you a clean place to attach a booking after the fact.

## Run

```bash
uv sync --python 3.12
uv run uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000`.

## MVP Flow

1. Create a `Trip`.
2. Choose whether it is `one_time` or `weekly`.
3. Add ranked `Route Options`.
4. Use `Trips` to manage weekly recurring trips at the parent level and review all dated scheduled trips below them.
5. Use `Trackers` to review each route option’s airport-pair Google Flights links.
6. Run the background fetch job to populate current prices.
7. Record bookings in the app.
8. Let the app continue comparing booked prices against tracker prices.

Legacy fallback:

1. Keep using `Imports` only if you still want the Google-tracked-link email flow.
2. Paste an exact tracked link into a tracker’s `Legacy manual tracker link` section if needed.
3. Import `.eml` alerts as before.

For travel that already happened:

1. Use `Log past trip` from the Trips workspace.
2. Enter a label and past date.
3. Save it into `Past trips`, with an optional jump directly into `Add booking`.

## Tests

```bash
uv run pytest -q
```

## Background Fetch

Run a conservative Google Flights batch:

```bash
uv run python -m app.jobs.fetch_google_flights --max-targets 3
```

Useful for quick testing:

```bash
uv run python -m app.jobs.fetch_google_flights --max-targets 1 --no-sleep
```
