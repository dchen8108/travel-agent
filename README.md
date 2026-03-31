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

## Core Objects

- `Trip`: top-level travel construct with a unique label
- `Route Option`: ranked tracker definition under a trip
- `Trip Instance`: one dated occurrence of a trip
- `Tracker`: one Google Flights tracker/search envelope for a route option on a trip instance
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
3. Add ranked `Route Options`.
4. Open generated Google Flights links and enable `Track prices`.
5. Import Google Flights `.eml` alerts as they arrive.
6. Review `Today`, `Trips`, and `Bookings`.
7. Record bookings in the app.
8. Let the app continue comparing booked prices against tracker signals.

## Tests

```bash
uv run pytest -q
```
