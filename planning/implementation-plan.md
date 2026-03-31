# travel-agent MVP Implementation Plan

## Goal

Ship a local MVP that is usable today on one machine.

Status on March 31, 2026:

- completed: project scaffold, local storage, rules flow, tracker management, manual `.eml` import, parser/matcher, review queue, booking capture, and server-rendered UI
- deferred: Gmail IMAP, outbound digest email, and calendar page

The first version is successful if the user can:

- define one recurring flight program
- generate upcoming trips and outbound/return price-tracking tasks
- import a Google Flights `.eml` alert
- map safe observations to trip segments
- record a booking
- see `set up`, `act now`, `booked`, and `rebook` states on a single dashboard

## Final MVP Boundary

Included:

- Python 3.12 local app using `uv`
- FastAPI + Jinja + htmx
- CSV/JSON storage under `data/`
- manual Google Flights tracker setup
- manual Google Flights link paste
- manual `.eml` import
- segment-level observation parsing and matching
- manual review queue for ambiguous imports
- booking capture
- trip recommendation rollup

Deferred:

- Gmail IMAP
- email digest sending
- calendar page
- phone-specific access
- credits

## Implementation Order

### 1. Skeleton

- initialize `pyproject.toml`
- create `app/`, `data/`, `tests/`, and template/static folders
- add settings, app factory, and health route
- add storage layer for CSV/JSON bootstrap and writes

### 2. Core Models and Services

- define typed models for programs, trips, trackers, bookings, email events, observations, and review items
- implement repository helpers for load/save operations
- implement trip generation from one recurring program
- implement tracker generation for outbound and return segments

### 3. Email Import Path

- build file upload route for `.eml`
- preserve raw `.eml` in `data/imported_emails/`
- parse Google Flights email into candidate observations
- write `email_events.csv`
- auto-match only clear route/date tracker matches
- create `review_items.csv` rows for ambiguous or unmatched candidates

### 4. Recommendation Engine

- compute latest per-segment observations
- roll outbound and return into a trip-level current total
- derive `needs_tracker_setup`, `wait`, `book_now`, `booked_monitoring`, and `rebook`
- attach short explanations to each trip

### 5. UI

- `Today`
- `Price Tracking`
- `Trip Detail`
- `Rules`
- `Add Booking`
- `Review`

### 6. Verification and Polish

- seed a local sample program
- import the known Google Flights sample email
- verify parser outputs and dashboard updates
- add tests for parser, matcher, trip generation, and recommendation logic
- review code and fix issues before commit

## Quality Gates

Before the MVP is considered usable:

- app boots with one command
- data directory auto-initializes cleanly
- known sample `.eml` imports without crashing
- at least one observation is matched into a tracker
- ambiguous observations land in review instead of being misapplied
- a booking can be recorded and rebook logic recomputes correctly
