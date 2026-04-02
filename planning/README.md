# Planning

This directory mixes current operational notes with older design docs from the v0 iteration. The repo has moved significantly since the early planning files were written.

## Current References

Use these first when you need the implementation as it exists today:

- `agent-checkpoint.md`: current product/runtime snapshot and bootstrap guide for a fresh agent
- `sqlite-storage.md`: current SQLite-backed storage model and runtime layout
- `gmail-booking-ingestion.md`: current Gmail booking automation pipeline
- `v1-ui-pass.md`: the recent UI/UX consolidation direction
- `trip-groups-and-recurring-rules.md`: proposed direction for decomposing recurring trips into groups + rules

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
- `Trip` is the top-level planning object
- trips can be `one_time` or `weekly`
- weekly trips own rolling scheduled instances
- one-time trips use their scheduled-trip page as the canonical operational surface
- route options are ranked tracker definitions under a trip
- bookings are trip-scoped, not tracker-scoped
- unmatched bookings are handled inline on `Bookings`, not through a separate primary `Resolve` workspace
- Gmail booking automation is incremental and checkpointed
- runtime data is stored in SQLite, while checked-in config lives under `config/`
