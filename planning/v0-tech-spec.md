# travel-agent v0 Tech Spec

## Objective

Implement a local-first web app that helps one user manage recurring commute flights using:

- a local control-panel website
- local CSV and JSON storage
- Google Flights tracking as the upstream price signal
- Google Flights email ingestion as the main data feed

This version is intentionally optimized for:

- no paid fare APIs
- no database
- no SPA frontend
- no scraper

The hardened baseline is:

- manual Google Flights tracker setup
- manual tracker-link paste when generated links are insufficient
- manual `.eml` upload

Automatic Gmail IMAP polling is an upgrade path, not a prerequisite for the first usable MVP.

After validating a real Google Flights email, the architecture should assume that Google signals are one-way route-and-date observations. The app should therefore model each saved rule as one directional commute pattern with one or more ranked schedule slots, then roll the best slot-level signals into trip-level decisions.

## Architecture Summary

v0 consists of four layers:

1. `Web UI`
   FastAPI server-rendered pages for rules, trackers, trips, and bookings.

2. `Storage`
   CSV and JSON files under `data/`, written atomically by the app service layer.

3. `Ingestion and recommendation jobs`
   Local commands that import Google Flights emails, update observations, and recompute trip states.

4. `Upstream signal source`
   Official Google Flights price tracking, configured manually by the user.

## Stack

### Runtime and Packaging

- Python 3.12+
- `uv` for environment and dependency management

### Web App

- FastAPI
- Uvicorn
- Jinja2 templates through FastAPI templating
- htmx for small inline interactions
- plain CSS or a tiny vendored CSS file

### Validation and Configuration

- Pydantic for model validation
- `pydantic-settings` or a small local settings wrapper if env-based config is needed

### Email and Scheduling

- Python standard library `email` package for parsing messages
- `launchd` later, once the manual-import MVP is stable

### File Handling

- Python standard library `csv`
- Python standard library `json`
- Python standard library `pathlib`

## Why This Stack

- no Node build chain is required
- local file storage is easy to inspect and back up
- the UI needs forms, lists, and status cards, not a rich client app
- Python is a strong fit for recurring jobs, email parsing, and local tooling

## Proposed Repository Layout

```text
travel-agent/
  app/
    main.py
    settings.py
    routes/
      today.py
      trackers.py
      imports.py
      trips.py
      rules.py
      bookings.py
    services/
      programs.py
      trip_instances.py
      trackers.py
      bookings.py
      recommendations.py
      review.py
    ingestion/
      google_flights_email_parser.py
      observation_matcher.py
    storage/
      csv_store.py
      json_store.py
      uploaded_email_store.py
      file_lock.py
    models/
      app_state.py
      program.py
      trip_instance.py
      tracker.py
      booking.py
      email_event.py
      fare_observation.py
      alert.py
      review_item.py
    templates/
      layout.html
      today.html
      trackers.html
      trip_detail.html
      rules.html
      add_booking.html
      review.html
      partials/
    static/
      app.css
    jobs/
      generate_trip_instances.py
      recompute_trip_states.py
      import_email_file.py
  data/
    imported_emails/
  planning/
  scripts/
  tests/
```

## Core Application Flows

### 1. Program Setup

1. User opens `Rules`.
2. User creates or edits one or more saved rules.
3. Each rule represents one directional commute pattern.
4. Major inputs are constrained to hardcoded airport, airline, weekday, and fare-preference catalogs.
5. App saves `programs.csv`.
6. App generates future `trip_instances.csv` rows and slot-level `trackers.csv` rows.

Generation rules:

- one rule -> one trip row per future week and route pairing
- each trip row -> one tracker per ranked slot that is still in the future

### 2. Tracker Setup

1. User opens `Trackers`.
2. App shows generated Google Flights links for each ranked slot and allows manual link paste.
3. User opens the link or pastes a better one and turns on `Track prices` in Google Flights.
4. User clicks `Mark tracking enabled` in the app.
5. Tracker status changes from `needs_setup` to `tracking_enabled`.

### 3. Email Ingestion

1. Google Flights sends an email when it has a tracked price update.
2. User uploads a `.eml` file.
3. The parser extracts route, dates, airline, airport-pair text, and price signals.
4. The raw `.eml` file is preserved under `data/imported_emails/`.
5. Parsed email metadata is stored in `email_events.csv`.
6. A matcher attempts to convert parsed segments into `fare_observations.csv` rows.
7. A segment is only auto-matched when `(origin_airport, destination_airport, travel_date)` resolves to exactly one tracker.
8. If matching is ambiguous, the event is marked `needs_review` and no tracker is updated automatically.
9. Safe matches update `trackers.csv` first, then the owning `trip_instances.csv` rows are recomputed.

### 4. Recommendation Refresh

1. App reads trip instances, trackers, bookings, and latest observations.
2. App rolls slot observations up to the trip level and recomputes trip status and explanation.
3. Updated cards appear on `Today`, `Calendar`, and `Trip Detail`.

### 5. Booking Capture

1. User manually books outside the app.
2. User records the booking in `Add Booking`.
3. App writes `bookings.csv`.
4. Future observations for the trip are evaluated against booked price to detect `rebook`.

## Routes

### Pages

- `GET /`
  Today dashboard.

- `GET /trackers`
  Price tracking and setup status.

- `GET /imports`
  Email import utility and recent import results.

- `GET /trips/{trip_instance_id}`
  Single trip detail page.

- `GET /rules`
  Multi-rule editor with constrained selectors and ranked time-slot support.

- `GET /bookings/new`
  Add booking form.

- `GET /review`
  Manual review queue for unmatched or ambiguous email imports.

### Actions

- `POST /rules`
  Save one rule by `program_id` and regenerate trip instances for all active rules.

- `POST /trackers/{tracker_id}/mark-enabled`
  Mark a tracker as enabled by the user.

- `POST /trackers/{tracker_id}/paste-link`
  Save a pasted Google Flights URL for a tracker.

- `POST /bookings`
  Save a booking.

- `POST /emails/upload`
  Manual `.eml` import.

- `POST /review/{email_event_id}/match`
  Resolve an ambiguous parsed observation to a tracker manually.

## Background Jobs

### `generate_trip_instances`

Purpose:

- expand recurring rules into concrete trip instances
- create missing segment tracker rows for the lookahead window

Run:

- after saving rules
- optionally once per day

### `import_email_file`

Purpose:

- import one `.eml` file from disk
- parse and persist structured email events
- convert parsed events into fare observations when matching is safe

### `recompute_trip_states`

Purpose:

- derive `needs_tracker_setup`, `wait`, `book_now`, `booked_monitoring`, and `rebook`
- update trip explanations and best-known values

Run:

- after email sync
- after booking entry
- after rules changes

### `daily_run`

Purpose:

- optional later wrapper once scheduled automation is added

Suggested later order:

1. generate trip instances
2. import new emails
3. recompute trip states

## Storage and Write Semantics

The MVP should use single-writer semantics:

- all mutations go through the app service layer or explicit import commands
- request handlers should not write the same file concurrently
- background jobs should not run at the same time as request-time mutations in the first version

CSV and JSON writes should be atomic:

- write to a temp file in the same directory
- rename into place once fully written

Append-only artifacts:

- `fare_observations.csv`
- preserved `.eml` files under `data/imported_emails/`

Projected files:

- `trip_instances.csv`
- `trackers.csv`

`fare_observations.csv` and `bookings.csv` are the canonical inputs for recommendation recompute. Trip and tracker “latest” fields are cached projections written only by the recompute/import path.

## Recommendation Logic

The MVP should use simple, explicit heuristics.

### `needs_tracker_setup`

Use when:

- a trip instance has no tracker
- or a tracker exists but was never marked enabled

### `wait`

Use when:

- one or both segment trackers are active
- there is no booking yet
- the latest observed signal does not justify action

### `book_now`

Use when:

- segment tracker coverage is good enough for the trip
- there is no booking yet
- the combined latest segment fare is attractive relative to recent observations
- and the trip is inside the configured booking horizon

Initial heuristic:

- combined latest segment fare is the lowest known combined fare for the trip, or within a small delta of it
- and the observation is recent

### `booked_monitoring`

Use when:

- a booking exists
- the combined latest segment fare is not lower by at least the configured rebook threshold

### `rebook`

Use when:

- a booking exists
- the combined latest segment fare is lower than `booked_price - rebook_alert_threshold`

## Email Ingestion Design

### Baseline

The guaranteed v0 path is manual `.eml` upload or pasted email content.

This removes account-auth dependencies from the first working version.

### Optional Upgrade

If the user uses Gmail, IMAP polling can automate ingestion later.

### Setup

For the MVP:

- the user saves the raw Google Flights email as `.eml`
- the user imports the `.eml` through the app

### Parsing Strategy

The parser should be conservative.

It should try to extract:

- one or more route/date sections
- one or more tracked-flight observations
- airline when present
- latest observed price
- price direction and previous price when present
- origin and destination airport code pair when present in the tracked-flight line
- message identifiers and subject for deduplication and auditability

If parsing is uncertain:

- store the raw event as `needs_review`
- do not silently invent structured fields
- surface the unresolved message in the UI for manual correction later

### Matching Strategy

The safest matching strategy is:

1. parse each email into candidate one-way observations
2. normalize airport-pair text and travel date
3. find trackers whose route and date align exactly
4. auto-match only when there is one clear tracker target
5. send ambiguous items to manual review

The matcher should not depend on airline name or time text to decide ownership. Those fields are helpful for display, but route, date, and segment direction should control matching.

## Storage Design Notes

- CSV remains the system of record for list-like data
- `app.json` stores config and sync state
- raw `.eml` files are preserved on disk and referenced from `email_events.csv`
- `email_events.csv` exists even if parsing is partial, to preserve raw evidence
- `fare_observations.csv` stays append-only

## Phone Access

The MVP does not need phone-specific features beyond the user's existing Google Flights notifications and access to the local dashboard on the same machine.

## Known Risks

### 1. Google Flights email structure

The first real sample shows:

- one email can contain multiple tracked routes
- tracked flights are presented as one-way route/date observations
- the plain-text body includes airline, times, route code pair, current price, and prior price

The MVP should therefore assume only:

- route/date/price are safe anchors when present
- airline and itinerary text are helpful but non-authoritative
- ambiguous matches must stay pending until reviewed

### 2. Alert frequency

Google Flights may not notify on every small price movement.

That means this v0 may be more “important-change aware” than “micro-optimization perfect.”

### 3. Manual tracker setup

Manual Google Flights tracker setup is the largest UX burden, so the product must make setup status obvious and require as little in-app bookkeeping as possible.

## Recommended Build Order

1. Project scaffold, settings, and file storage.
2. Rules form plus trip and tracker generation.
3. Manual `.eml` import and raw email persistence.
4. Google Flights parser and observation matcher.
5. Recommendation engine and booking capture.
6. Today, Price tracking, Trip detail, and review queue UI.
7. Polish, tests, and sample data.

The user still has to turn on tracking in Google Flights for each trip instance.

That setup burden is acceptable for v0 but should be visible in the product.

### 4. Gmail-specific automation

Automated ingestion is easiest with Gmail IMAP.

If the user does not use Gmail, the fallback is manual `.eml` upload or pasted email text.

## Access Needed From The User

There is no Google Flights API key for this plan.

To validate and then implement the free-only path, the most useful things the user can provide are:

- at least one real Google Flights price-tracking email
- ideally the raw `.eml` file for that email
- if automatic Gmail sync is desired, a Gmail account that receives those alerts

If Gmail IMAP is used:

- personal Gmail can work with IMAP, and app-password-based access may be needed if the app does not use `Sign in with Google`
- app passwords require 2-Step Verification on the Google Account
- Google Workspace should be treated as OAuth-only for automatic inbox sync

Because of this:

- manual `.eml` upload remains the guaranteed first implementation path
- Gmail IMAP automation should only be attempted immediately if the user confirms the mailbox is personal Gmail and is comfortable with the auth setup

## POC Checklist Before Implementation Expands

Before building too much, verify:

1. A real Google Flights tracking email can be captured locally.
2. The parser can reliably extract one or more route/date sections and one or more tracked-flight observations from at least a few examples.
3. The extracted observations are sufficient to map into real segment trackers.
4. A booked-trip comparison against later emails can drive a believable segment-summed `rebook` recommendation.
5. Manual tracker-link paste is enough if generated Google Flights links are imperfect.

If those checks fail, the architecture should be revisited before deeper build-out.
