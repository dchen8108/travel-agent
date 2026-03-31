# travel-agent v0 Product Spec

## Goal

Build a local-first personal tool that helps one traveler manage Google Flights trackers and bookings in one place.

The MVP should answer:

1. What trips am I tracking?
2. What bookings do I already have?
3. Which upcoming trip instances still need attention?
4. Which booked trip instances are now cheaper than what I paid?

This version should work end to end for one user without paid fare APIs, hotels, credits, Gmail automation, or auto-booking.

## Product Positioning

`travel-agent` is a tracker-of-trackers.

It does not replace Google Flights. It organizes the Google Flights tracking the user already relies on and ties that tracking to a small, structured travel model:

- named trips
- ranked route options
- dated trip instances
- tracker setup state
- bookings

The product should feel like a control panel for recurring and one-off flight travel rather than a search engine.

## External Signal Model

v0 uses official Google Flights price tracking as the upstream signal source.

The product assumes:

- trackers are created manually by the user in Google Flights
- Google Flights alert emails provide low-cost price observations
- tracker signals can be noisy and incomplete

The app therefore distinguishes between:

- `high-signal` user commitments, such as bookings
- `low-signal` upstream noise, such as unmatched or ambiguous tracker emails

Only unmatched bookings should require user resolution. Unmatched tracker signals should be ignored or logged quietly.

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
  - one time window
- rolling 12-week generation for weekly trips
- trip-instance management, including skipping one occurrence
- tracker management
- manual Google Flights link paste
- manual `.eml` upload
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
- Google Flights scraping
- generalized review queue for unmatched tracker imports
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

Examples:

- `LA to SF Outbound`
- `SF to LA Return`
- `Conference Monday Arrival`

### Route Option

A ranked tracker definition under a trip.

Each route option corresponds roughly 1:1 with one Google Flights tracker/search envelope.

A route option includes:

- one or more origin airports
- one or more destination airports
- one or more airlines
- a relative day from the trip anchor date
- a single time window

All route options are implicitly nonstop-only for v0.

### Trip Instance

One dated occurrence of a trip.

- one-time trips create exactly one instance
- weekly trips maintain the next 12 future instances
- in the product UI, trip instances are the scheduled trips the user actually acts on

### Tracker

One tracker row per route option per trip instance.

Trackers represent the Google Flights setup and incoming signal state for that dated route option.

### Booking

One purchased itinerary attached to a trip instance, and ideally to the matching tracker.

### Unmatched Booking

Temporary holding state for bookings that cannot be attached confidently.

Only unmatched bookings should appear in `Resolve`.

## Anchor Date and Relative Day Model

Every trip instance has an `anchor_date`.

Every route option stores a `day_offset` relative to that anchor date, rather than an absolute weekday.

Examples:

- `T-1`
- `T`
- `T+1`

The UI should present these options in a friendly form such as:

- `Sunday (T-1)`
- `Monday (T)`
- `Tuesday (T+1)`

The actual stored value should remain an integer offset, so there is no ambiguity about whether a route option means the day before or the day after the anchor date.

## Recurring Trip Rules

Weekly trips must be persistent parent objects.

The app should:

- keep the trip label and route options at the parent level
- maintain the next 12 future instances continuously
- add a newly in-scope 12th week as time moves forward
- allow a single occurrence to be skipped without changing the recurring parent
- allow the recurring trip to be edited, paused, or deleted

## Core User Flows

### 1. Trip-first

Happy-path setup.

1. User creates a trip label.
2. User chooses `one_time` or `weekly`.
3. User enters ranked route options.
4. App creates the trip.
5. App generates one or more trip instances.
6. App creates one tracker per route option per trip instance.
7. User sets up Google Flights tracking for the generated trackers.

### 2. Booking-first

User already has a booking and wants it tracked.

1. User records or imports a booking.
2. App attempts to match it to an existing trip instance and tracker.
3. If the match is confident, attach automatically.
4. If not, create an unmatched booking record.
5. User resolves the unmatched booking by:
   - linking it to an existing trip instance
   - or creating a new one-time trip from the booking

## Product Principles

- Trips are the main object, not rules.
- Trackers are operational detail, not the primary mental model.
- Show a small number of actionable states.
- Never ask the user to resolve tracker noise.
- Only ask the user to resolve real travel commitments.
- Keep recurring-trip management first-class.
- Make the Google Flights setup burden explicit instead of pretending it is automated.

## Information Architecture

The MVP should include these primary screens:

1. `Today`
2. `Trips`
3. `Bookings`
4. `Imports`
5. `Resolve`

The `Trips` screen should be split into:

- `Recurring trips`: weekly parent plans with edit/pause controls
- `Scheduled trips`: every dated trip instance, including standalone one-time trips and recurring-generated occurrences
  The scheduled list should support:
  - filtering by one or more recurring trips
  - a `Show skipped trips` toggle
  - restoring skipped trips inline when they are visible

Optional operational surface:

6. `Trackers`

`Today` should be the landing page.

`Resolve` should appear only when unmatched bookings exist.

## Screen Requirements

### 1. Today

Purpose:

- show what still needs attention
- summarize tracker setup gaps
- surface booked trips that are now cheaper

Required summary metrics:

- trips needing tracker setup
- open trip instances
- booked trip instances under monitoring
- unmatched bookings

Required sections:

- `Needs setup`
- `Open trips`
- `Booked trips`

### 2. Trips

Purpose:

- manage one-time and weekly trips
- edit recurring definitions
- inspect generated occurrences

Recurring trip actions:

- `Edit`
- `Pause`
- `Delete`
- `View instances`

Trip instance actions:

- `View`
- `Skip`
- `Restore`

### 3. Bookings

Purpose:

- show existing bookings
- add new bookings
- make booking linkage obvious

### 4. Imports

Purpose:

- import Google Flights `.eml` files
- show what signals were accepted
- keep the raw email artifact

Unmatched tracker observations should not create user-facing work.

### 5. Resolve

Purpose:

- handle unmatched bookings only

Actions:

- `Link to existing trip instance`
- `Create new one-time trip`

### 6. Trackers

Purpose:

- operational visibility into Google Flights setup
- easy access to generated or pasted links

This is useful, but subordinate to `Trips`.

## MVP Success Criteria

The MVP is successful if the user can:

- create and manage one-time and weekly trips
- maintain ranked route options under each trip
- see the next 12 weekly occurrences automatically
- skip one weekly occurrence without deleting the whole recurring trip
- open or paste Google Flights tracker links
- import real Google Flights `.eml` alerts without crashing
- record bookings
- auto-link easy bookings
- resolve only unmatched bookings
- view open, booked, skipped, and rebook-worthy trip instances in one place
