# Planning

This directory is for current operational and architecture notes only. Old planning snapshots that no longer describe the live product should live in git history, not in the active repo.

## Current References

Use these first when you need the implementation as it exists today:

- `agent-checkpoint.md`: current product/runtime snapshot and bootstrap guide for a fresh agent
- `sqlite-storage.md`: current SQLite-backed storage model and runtime layout
- `gmail-booking-ingestion.md`: current Gmail booking automation pipeline
- `trip-groups-and-recurring-rules.md`: transition-era architecture notes; useful context, but not an exact schema reference

The top-level [README.md](/Users/davidchen/code/travel-agent/README.md) is the main source of truth for:

- current runtime architecture
- launchd jobs
- Gmail booking automation
- background fetch behavior
- storage/config layout

## Secondary References

These are still useful, but they are more focused background than canonical implementation docs:

- `google-flights-poc.md`
- `trip-groups-and-recurring-rules.md`
- `v1-ui-pass.md`

## Current Product Baseline

- `travel-agent` is a local-first recurring flight control panel
- `Trip Group` is a pure organizational bucket for concrete scheduled trips
- `Trip` can be a one-time trip or a recurring rule authoring object
- the normal UI requires recurring rules to belong to at least one group
- scheduled trips can belong to zero or more groups and at most one rule
- attached recurring instances inherit rule group targets; detached instances freeze them
- the dashboard at `/` is the canonical operational surface
- collection inspection happens inline on dashboard collection cards
- trip inspection happens inline on dashboard rows plus bookings/trackers modal panels
- `/groups/{id}`, `/trip-instances/{id}`, and `/trips/{id}` are compatibility redirects into dashboard anchors, dashboard panels, or edit flows
- route options are ranked tracker definitions under a trip
- bookings are trip-scoped and can optionally link to a uniquely matched route option
- unlinked bookings are handled inline on the dashboard, not through a separate primary `Resolve` or `Bookings` workspace
- Gmail booking automation is incremental and checkpointed
- runtime data is stored in SQLite, while checked-in config lives under `config/`

## Current Hygiene Notes

- there is no active legacy CSV/JSON import path in the app anymore; historical snapshots that were once kept under `legacy/` were removed from the repo and should be recovered from git history if ever needed
- compatibility URLs like `/trips`, `/bookings`, and `/trackers` still exist only as redirects; new work should target the dashboard and the real detail/create routes
- older planning docs that stopped matching the live product were removed from this directory; use git history if you need that context
