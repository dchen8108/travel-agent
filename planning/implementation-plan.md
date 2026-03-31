# travel-agent MVP Implementation Plan

## Goal

Ship a local MVP that is usable today on one machine and reflects the current product direction.

The first usable version is successful if the user can:

- create one-time and weekly trips
- manage recurring trips over time
- maintain ranked route options under each trip
- see the next 12 weekly instances automatically
- set up Google Flights trackers for those instances
- import Google Flights `.eml` alerts safely
- record bookings
- let easy bookings attach automatically
- resolve only unmatched bookings
- view open, booked, skipped, and cheaper-than-booked instances in one place

## Final MVP Boundary

Included:

- Python 3.12 local app using `uv`
- FastAPI + Jinja
- CSV/JSON storage under `data/`
- trips-first information architecture
- one-time and weekly trips
- rolling 12-week recurring generation
- ranked route options
- manual Google Flights tracker setup
- manual Google Flights link paste
- manual `.eml` import
- safe observation matching
- booking capture
- unmatched booking resolution

Deferred:

- Gmail IMAP
- outbound digest email
- credits
- hotels
- paid fare APIs
- generalized tracker review queue

## Implementation Order

### 1. Planning reset

- rewrite planning docs around `Trip`, `Route Option`, `Trip Instance`, `Tracker`, and `Unmatched Booking`
- remove stale references to rules-first architecture and tracker review queue

### 2. Domain and storage rewrite

- replace `Program` with `Trip`
- add `RouteOption`
- add `UnmatchedBooking`
- reshape `TripInstance` states
- reshape `Tracker` to point to `route_option_id`
- update repository bootstrap for new CSV file set
- drop compatibility with earlier test data

### 3. Core services

- trip create/edit/delete/pause flows
- recurring-instance generation
- tracker synchronization
- booking attachment and unmatched booking creation
- recommendation rollup
- observation matching that ignores ambiguous tracker noise

### 4. UI rebuild

- `Today`
- `Trips`
- `Trip Detail`
- `Bookings`
- `Imports`
- `Resolve`
- `Trackers`

### 5. Verification

- parser tests
- generation tests
- booking matching tests
- resolve-flow tests
- smoke tests for key pages

### 6. Review and hardening

- run reviewer subagent on the implementation
- fix agreed issues
- rerun tests
- commit and push

## Quality Gates

Before the MVP is considered usable:

- app boots with one command
- repository bootstraps the new schema cleanly
- the old test data can be discarded without breaking startup
- a weekly trip produces 12 future instances
- skipping one occurrence persists
- tracker rows are created from ranked route options
- known Google Flights sample email imports without crashing
- ambiguous tracker observations are ignored instead of becoming user work
- unmatched bookings appear in `Resolve`
- linking an unmatched booking clears it from `Resolve`
- a cheaper matched observation can drive a booked instance into `rebook`
