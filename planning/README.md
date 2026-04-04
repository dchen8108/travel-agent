# Planning

This directory mixes current operational notes with older design docs from the v0 iteration. The repo has moved significantly since the early planning files were written.

## Current References

Use these first when you need the implementation as it exists today:

- `agent-checkpoint.md`: current product/runtime snapshot and bootstrap guide for a fresh agent
- `sqlite-storage.md`: current SQLite-backed storage model and runtime layout
- `gmail-booking-ingestion.md`: current Gmail booking automation pipeline
- `trip-groups-and-recurring-rules.md`: architecture notes for the group/rule transition; useful context, but not an exact schema reference

The top-level [README.md](/Users/davidchen/code/travel-agent/README.md) is the main source of truth for:

- current runtime architecture
- launchd jobs
- Gmail booking automation
- background fetch behavior
- storage/config layout

## Historical Design Docs

These files are still useful for intent and original tradeoffs, but they are not authoritative descriptions of the current product:

- `v0-product-spec.md`
- `v0-wireframes.md`
- `v0-data-model.md`
- `v0-tech-spec.md`
- `implementation-plan.md`
- `google-flights-poc.md`

Read them as historical design context, not current schema or route documentation.

## Current Product Baseline

- `travel-agent` is a local-first recurring flight control panel
- `Trip Group` is a pure organizational bucket for concrete scheduled trips
- `Trip` can be a one-time trip or a recurring rule authoring object
- the normal UI requires recurring rules to belong to at least one group
- scheduled trips can belong to zero or more groups and at most one rule
- attached recurring instances inherit rule group targets; detached instances freeze them
- one-time trips use their scheduled-trip page as the canonical operational surface
- route options are ranked tracker definitions under a trip
- bookings are trip-scoped and can optionally link to a uniquely matched route option
- unlinked bookings are handled inline on the dashboard, not through a separate primary `Resolve` or `Bookings` workspace
- Gmail booking automation is incremental and checkpointed
- runtime data is stored in SQLite, while checked-in config lives under `config/`

## Current Hygiene Notes

- there is no active legacy CSV/JSON import path in the app anymore; any `legacy/` artifacts in local working trees should be treated as user-local leftovers, not runtime inputs
- compatibility URLs like `/trips`, `/bookings`, `/resolve`, and `/trackers` still exist only as redirects; new work should target the dashboard and the real detail/create routes
