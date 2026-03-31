# travel-agent v0 Product Spec

## Goal

Build a personal, local-first tool that helps a recurring traveler answer three questions:

1. What flights should I book now?
2. What trips are safe to wait on?
3. What already-booked trips should I rebook because the price dropped?

This version should work end to end for one user without credits, hotels, auto-booking, or loyalty optimization.

## Product Positioning

`travel-agent` is not a generic flight search app.

It is a recurring-flight decision tool with a simple control panel and async notifications. The product should feel like a personal travel analyst that keeps watch over the next several weeks of commute flights and points out the small set of decisions that matter.

For the free-only v0, the app does not buy fare data directly. Instead, it uses official Google Flights tracking as the upstream signal source and turns those signals into a personal workflow.

## Primary User

A traveler with repeated flight patterns who:

- pays out of pocket
- books flights several weeks ahead
- prefers a small set of airlines
- usually buys flexible fares
- is willing to rebook for moderate savings
- wants to stop checking prices manually every day

## External Signal Model

v0 relies on Google Flights tracking rather than a paid fare API.

The intended flow is:

- the app generates or accepts pasted Google Flights links for each upcoming trip instance
- the user turns on `Track prices` in Google Flights
- Google Flights sends email and mobile alerts
- the app ingests those emails and stores price observations
- the app uses those observations plus booking data to recommend `book now`, `wait`, or `rebook`

This is a deliberate product decision to keep v0 free and operationally simple.

Based on a real Google Flights alert email, v0 should assume that tracking signals arrive per one-way route and date rather than as a neat round-trip package. The app should therefore model tracked price signals at the ranked route-option level and roll them up into trip-level recommendations.

## v0 Scope

In scope:

- one user
- one or more recurring flight rules
- each rule is one-way only
- multiple ranked route options per rule
- each route option chooses one origin airport, one destination airport, one weekday, one time window, one airline, and a nonstop toggle
- Google Flights link generation or manual tracker-link paste
- tracker setup and tracker-status visibility
- manual Google Flights email upload
- booked-trip monitoring
- rebook recommendations
- local web interface
- local-file storage

Out of scope:

- travel credits
- hotels
- points or award travel
- auto-booking
- airline account integrations
- direct fare-provider integrations
- Google Flights scraping
- chatbot-first interface
- multi-user support
- Gmail IMAP automation
- daily digest email

## Core User Loop

1. The user defines one or more recurring flight rules.
2. The system generates the next 12 weeks of trip instances.
3. The system generates Google Flights search links for those trip instances or lets the user paste exact tracker links.
4. The user turns on tracking in Google Flights for the ranked route options they care about.
5. Google Flights sends email and phone alerts when prices move.
6. The user uploads those emails into the app as `.eml` files.
7. The app labels each trip as `wait`, `book now`, `booked_monitoring`, or `rebook`.
8. The user books manually outside the tool.
9. The user records the booking in the tool.
10. The app keeps monitoring booked trips through subsequent Google Flights alerts.
11. The dashboard and review queue summarize what matters now.

## Product Principles

- Show recommendations, not search-result dumps.
- Default to one primary action per trip.
- Explain every recommendation in one sentence.
- Make the next 12 weeks visible at a glance.
- Keep state entry simple enough that the user will actually maintain it.
- Design the web app as a control panel, not a booking engine.
- Use official upstream signals before adding unofficial scraping.
- Degrade gracefully when incoming signals are sparse or ambiguous.

## Information Architecture

The first usable MVP should include 7 screens:

1. `Today`
2. `Trackers`
3. `Imports`
4. `Review`
5. `Trip Detail`
6. `Rules`
7. `Add Booking`

`Today` should be the landing page.

`Calendar` is useful, but it is not required to make the product usable today. It should be deferred until the core ingest -> recommend -> book -> reprice loop is stable.

## Screen Requirements

### 1. Today

Purpose:

- surface the small set of trips that matter right now
- summarize current risk and savings opportunities
- show tracker gaps that block good recommendations

Required summary strip:

- trips that need setup
- trips that need action now
- booked trips being monitored
- open review items

Required sections:

- `Set up price tracking`
- `Act now`
- `Booked trips`

Each trip card must include:

- route and dates
- tracking status for the segments that actually apply
- latest observed price if available
- signal timestamp if available
- status badge
- one-line rationale
- primary action

Primary actions by section:

- `Set up price tracking`: `Open Google Flights`, `Paste link`, `I turned tracking on`
- `Act now`: `View details`, `Mark booked`
- `Booked trips`: `View details`, `Mark rebooked`, `Update booking`

Global utility actions:

- `Import Google Flights email`
- `Add booking`

### 2. Trackers

Purpose:

- manage the Google Flights setup burden explicitly
- make it obvious which trips are fully monitored versus partially monitored

Trackers should be modeled per ranked route option inside a one-way rule.

The page should group segments by trip and by setup state:

- `Needs setup`
- `Awaiting first signal`
- `Active`
- `Stale`

Each route-option row must include:

- rank label, route detail summary, and date
- generated or pasted Google Flights link
- tracker status
- first enabled timestamp if known
- last signal timestamp if known
- latest observed price if known

Tracker statuses:

- `needs_setup`
- `tracking_enabled`
- `signal_received`
- `stale`

Required actions:

- `Open Google Flights`
- `Paste Google Flights link`
- `I turned tracking on`
- `View trip`

### 3. Imports

Purpose:

- bring Google Flights alert emails into the app
- show what matched safely and what needs manual review

Requirements:

- upload `.eml` files
- preserve imported email artifacts
- show parsed observations from the email
- auto-match observations to segment trackers when exact matching is possible
- place unmatched observations into a review queue

Required actions:

- `Upload .eml`
- `Review unmatched observations`
- `Open related trip`

### 4. Review

Purpose:

- resolve ambiguous or unmatched observations safely
- keep price signals from being silently applied to the wrong trip

Requirements:

- group open review items by source email
- show route, date, airline, price, and itinerary context
- offer only candidate trackers that match the observed route and date
- allow the user to ignore a bad or irrelevant observation

### 5. Trip Detail

Purpose:

- explain the recommendation
- compare booked versus current price when relevant
- capture the user action on a single trip

For unbooked trips, show:

- trip summary
- tracker status
- current recommendation
- latest Google Flights observation
- recent observed prices
- one-paragraph explanation

For booked trips, show:

- booked flight summary
- booked price
- latest comparable observation
- estimated savings if rebooked
- rebook recommendation
- recent observed prices

Required actions:

- `Open Google Flights`
- `Mark booked`
- `Update booking`
- `Mark rebooked`
- `Mark cancelled`

### 6. Rules

Purpose:

- define how the recurring travel rules behave

The rule model should stay flat:

- one saved rule row per recurring pattern
- multiple rules allowed
- use multiple one-way rules when outbound and return preferences differ

Required fields:

- rule name
- ranked route options
- active / paused toggle

Major selectors should be constrained:

- airports come from a supported searchable catalog
- airlines come from a supported constrained selector
- weekdays are dropdowns
- each route option owns its own airport, airline, weekday, time-window, and nonstop settings
- ranked options can be reordered, duplicated, and removed

The MVP should not require mailbox configuration. Automatic Gmail sync is a later enhancement.

The screen should optimize for clarity over flexibility. Advanced rules can wait until later.

### 7. Add Booking

Purpose:

- move a trip from recommendation mode into monitoring mode

Entry methods:

- manual form entry
- paste itinerary text

Minimum fields:

- trip instance
- booked price
- booking date

Optional fields:

- airline
- outbound flight summary
- return flight summary
- fare type
- record locator
- notes

## Recommendation Model

v0 recommendations should map to a small vocabulary:

- `needs_tracker_setup`
- `book_now`
- `wait`
- `booked_monitoring`
- `rebook`

Each recommendation needs:

- status
- headline
- short explanation
- latest observed price when available
- last updated timestamp

Recommendations are derived from:

- recurring trip rules
- Google Flights tracker status
- observed Google Flights email signals
- recorded bookings

The recommendation engine should treat Google Flights observations as price signals first and itinerary context second. The MVP should not depend on perfect fare-family parsing from the email body.

For one-way rules with multiple ranked route options, the app should choose the best currently observed option and use that for trip-level recommendations.

### Needs Tracker Setup

Use when:

- a trip instance has no confirmed Google Flights tracker
- there is no reliable signal source for that trip yet

### Book Now

Use when:

- the trip is within the fixed 12-week planning horizon
- a recent Google Flights observation indicates an attractive fare
- the latest signal is strong enough to act on now

### Wait

Use when:

- the trip is still early or unusually expensive
- there is no compelling recent signal that justifies booking
- tracker coverage exists, but the latest observations do not justify booking yet

### Booked Monitoring

Use when:

- the trip is booked
- the latest observed comparable fare does not justify action

### Rebook

Use when:

- the trip is booked
- a newer comparable fare is lower
- the price drop is at or above the user threshold

## Notification Design

There are two notification surfaces in v0:

- Google Flights notifications and emails for upstream price alerts
- an in-app digest on the Today page

Notification types:

- daily digest
- Google Flights price alerts

The app does not need to duplicate every upstream alert. It should instead summarize them and surface actionable recommendations.

### Daily Digest

Email digest can be added later. The MVP only needs the in-app digest and status summary on `Today`.

## Known Limitations

- The app only knows what Google Flights tells it or what the user records manually.
- It may miss small price changes that never trigger an upstream email.
- Tracker setup is manual in Google Flights.
- Email parsing may occasionally require manual correction.
- Generated Google Flights links are best-effort; manual tracker-link paste is the fallback.
- A single Google Flights email may contain multiple tracked routes and multiple flight observations, so parsing and matching must be segment-aware.
- The app should preserve raw imported emails and expose a small manual-review queue when a parsed observation cannot be matched safely.

## Success Criteria For v0

The product is successful if the user can:

- define a recurring commute program once
- generate and enable trackers for the next 8 weeks without confusion
- open the app and understand the next 8 weeks quickly
- record a booking in under 1 minute
- tell whether to book, wait, or rebook without opening multiple travel sites
- receive enough timely signal from Google Flights plus the daily digest to stay out of the weeds

## Explicit Non-Goals

v0 does not need:

- perfect fare prediction
- automatic booking
- complete coverage of every price movement
- perfect itinerary parsing
- a polished public-product UX
- support for every airline or route pattern

It only needs to make the repeated supercommuter booking loop materially easier and cheaper.
