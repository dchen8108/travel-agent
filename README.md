# travel-agent

Local-first recurring flight monitor for one user.

This MVP is built around the free Google Flights workflow:

- you save one or more recurring flight rules
- each rule is one-way and contains ranked route options
- the app generates future trip instances and one tracker per ranked route option
- you turn on `Track prices` in Google Flights manually
- you import Google Flights `.eml` alerts into the app
- the app rolls those route-option signals into `set up`, `act now`, `booked`, and `rebook` decisions

## Stack

- Python 3.12
- `uv`
- FastAPI
- Jinja templates
- local CSV/JSON storage under `data/`

## Run

```bash
uv sync --python 3.12
uv run uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000`.

## First-time flow

1. Open `Rules` and save your recurring flight rules.
   Use multiple one-way rules when your outbound and return preferences differ, and rank route options inside each rule.
2. Open `Trackers` and use the generated Google Flights links.
3. In Google Flights, turn on `Track prices` for each route option you care about.
4. When Google sends a price alert email, save it as `.eml`.
5. Import the `.eml` from `Imports`.
6. Review `Today` and `Review` for matched and ambiguous observations.
7. Record bookings through `Add booking` / `Record booking`.

## Tests

```bash
uv run pytest
```
