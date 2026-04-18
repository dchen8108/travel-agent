# Planning

This directory is for current operational and architecture notes only. Historical notes that no longer describe the live product belong under `planning/archive/` or in git history, not alongside active docs.

## Current References

Use these first when you need the implementation as it exists today:

- `agent-checkpoint.md`: current product/runtime snapshot and bootstrap guide for a fresh agent
- `sqlite-storage.md`: current SQLite-backed storage model and runtime layout
- `gmail-booking-ingestion.md`: current Gmail booking automation pipeline
- there are no active historical planning docs in this directory; recover old migration notes from `planning/archive/` or git history if needed

The top-level [README.md](/Users/davidchen/code/travel-agent/README.md) is the main source of truth for:

- current runtime architecture
- launchd jobs
- Gmail booking automation
- background fetch behavior
- storage/config layout

## Archive

These are historical references, not current source-of-truth docs:

- `archive/google-flights-poc.md`
- `archive/agent-refresh-prompt.md`

## Current Product Baseline

- `travel-agent` is a local-first recurring flight control panel
- `Collection` is a pure organizational bucket for concrete scheduled trips
- `Trip` can be a one-time trip or a recurring trip authoring object
- the normal UI requires recurring trips to belong to at least one collection
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
