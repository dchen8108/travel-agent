# travel-agent

Local-first tracker-of-trackers for recurring flight travel.

This MVP is built around a simple idea:

- you organize travel into named `Trips`
- each trip owns one or more ranked `Route Options`
- each route option corresponds to one Google Flights tracker/search definition
- the app generates dated `Trip Instances` and per-instance `Trackers`
- you manually turn on `Track prices` in Google Flights
- you import Google Flights `.eml` alerts into the app
- the app stores tracker signals, organizes bookings, and tells you what still needs attention

This version is intentionally local and simple:

- one user
- local CSV/JSON storage under `data/`
- one-time or weekly trips
- a rolling 12-week horizon for weekly trips
- manual Google Flights setup
- manual `.eml` upload
- no paid fare APIs
- no Gmail automation
- no credits or hotels
- a separate `Log past trip` flow for historical travel records

## Core Objects

- `Trip`: authoring object with a unique label
- `Route Option`: ranked tracker definition under a trip
- `Trip Instance`: one dated scheduled trip, either standalone or generated from a weekly trip
- `Tracker`: one Google Flights tracker/search envelope for a route option on a trip instance
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
5. Open generated Google Flights links and enable `Track prices`.
6. Import Google Flights `.eml` alerts as they arrive.
7. Record bookings in the app.
8. Let the app continue comparing booked prices against tracker signals.

For travel that already happened:

1. Use `Log past trip` from the Trips workspace.
2. Enter a label and past date.
3. Save it into `Past trips`, with an optional jump directly into `Add booking`.

## Tests

```bash
uv run pytest -q
```
