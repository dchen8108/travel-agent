# travel-agent v0 Product Spec

## Goal

Build a local-first personal tool that helps one traveler manage Google Flights searches and bookings in one place.

The MVP should answer:

1. What trips am I tracking?
2. What bookings do I already have?
3. Which upcoming trip instances still need attention?
4. What is the best current Google Flights price I know for each tracker?
5. Which booked trip instances are now cheaper than what I paid?

This version should work end to end for one user without paid fare APIs, hotels, credits, Gmail automation, or auto-booking.

## Product Positioning

`travel-agent` is a tracker-of-trackers.

It does not replace Google Flights. It organizes Google Flights searches and ties them to a small travel model:

- named trips
- ranked route options
- dated trip instances
- trackers
- bookings
- best known fetched price per tracker

The product should feel like a control panel for recurring and one-off flight travel rather than a search engine.

## Signal Model

v0 uses Google Flights links as the upstream price surface.

The product assumes:

- each tracker can be expanded into one or more concrete airport-pair Google Flights searches
- Travel Agent should query them conservatively in the background
- the background fetcher should behave like a light personal-use tool, not a high-frequency scraper

The app therefore distinguishes between:

- `high-signal` user commitments, such as bookings
- `medium-signal` background-fetched Google Flights prices

Only unmatched bookings should require user resolution.

## MVP Scope

In scope:

- one user
- local web app
- one-time trips
- weekly recurring trips
- unique trip labels
- ranked route options under each trip
- route options with:
  - multiple origin airports
  - multiple destination airports
  - multiple airlines
  - one relative travel day
  - one departure window
- route-option airport cap of 3 origins and 3 destinations
- rolling 12-week generation for weekly trips
- trip-instance management, including skipping one occurrence
- tracker management
- one generated Google Flights link per airport pair
- conservative background fetching
- tracker-level best-price rollup
- append-only fetched offer history
- booking capture
- automatic booking attachment when confident
- unmatched booking resolution
- local CSV/JSON storage

Out of scope:

- credits
- hotels
- points or award travel
- paid fare APIs
- Gmail IMAP polling
- aggressive scraping infrastructure
- round-trip trip definitions
- user-configurable lookahead horizon
- fare preference controls
- nonstop toggle

## Core Domain Model

### Trip

Top-level travel construct with a unique label.

Kinds:

- `one_time`
- `weekly`

### Route Option

A ranked tracker definition under a trip.

Each route option corresponds 1:1 with one user-facing tracker row.

A route option includes:

- one or more origin airports
- one or more destination airports
- one or more airlines
- a relative day from the trip anchor date
- a single departure window

All route options are implicitly nonstop-only for v0.

### Trip Instance

One dated occurrence of a trip.

- one-time trips create exactly one instance
- weekly trips maintain the next 12 future instances
- past instances are preserved in storage but hidden from the current MVP UI

### Tracker

One tracker row per route option per trip instance.

Trackers remain the planning and recommendation unit. They show the best known price among their underlying fetch targets.

### Tracker Fetch Target

One concrete airport-pair Google Flights search under a tracker.

This is an internal operational object. Users should mostly experience it as a set of short Google Flights links plus a rolled-up best price.

### Booking

One purchased itinerary attached to a trip instance, and ideally to the matching tracker.

### Unmatched Booking

Temporary holding state for bookings that cannot be attached confidently.

Only unmatched bookings should appear in `Resolve`.

## Product Principles

- Trips are the main object, not rules.
- Trackers are operational detail, not the primary mental model.
- Background fetching should feel passive and low-drama.
- Show a small number of actionable states.
- Never ask the user to resolve tracker noise.
- Only ask the user to resolve real travel commitments.
- Keep recurring-trip management first-class.

## Information Architecture

The MVP should include these primary screens:

1. `Today`
2. `Trips`
3. `Bookings`
4. `Resolve`

### Trips

The `Trips` screen should be split into:

- `Recurring trips`
- `Scheduled trips`

`Scheduled trips` should support:

- live search by trip label
- filtering by one or more recurring trips
- a pill-style `Show skipped` toggle
- restoring skipped trips inline when they are visible

### Trackers

Trackers should be accessed from a scheduled trip, not from a global page:

- `View trackers` on a scheduled trip opens a trip-specific tracker detail page
- one row per tracker
- a clear `Best price among selected airports` message
- one short link per airport pair, such as `LAX to SFO`
- visible refresh timing and price freshness
- a trip-specific `Refresh sooner` action
