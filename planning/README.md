# Planning

This directory holds the current product and technical plan for the `travel-agent` MVP.

The current design baseline is:

- `travel-agent` is a tracker-of-trackers
- the top-level object is a `Trip`, not a `Rule`
- trips can be `one_time` or `weekly`
- weekly trips are parent plans
- dated trip instances are the scheduled trips the user actually flies
- skipped trip instances are hidden by default and can be surfaced again through scheduled-trip filters
- route options are ranked tracker definitions under a trip
- each tracker can fan out into concrete airport-pair fetch targets
- the app now has a conservative in-house Google Flights fetcher
- the manual import path remains as a legacy fallback
- weekly trips maintain the next 12 future occurrences
- only unmatched bookings go to `Resolve`
- unmatched tracker noise is ignored

Current docs:

- `v0-product-spec.md`: product goals, MVP scope, information architecture, and user flows
- `v0-wireframes.md`: low-fidelity page structure and key interaction patterns
- `v0-data-model.md`: local-file schema for trips, route options, instances, trackers, bookings, and imports
- `v0-tech-spec.md`: stack, architecture, routes, services, and implementation boundaries
- `google-flights-poc.md`: what has been verified about Google Flights and what assumptions remain
- `implementation-plan.md`: concrete implementation order and quality gates
