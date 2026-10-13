# Parallel V2 Product Boundary

Status: parallel evaluation. V1 remains intact and is still the default operational experience.

## Product Intent

V2 tests a calmer information architecture without rebuilding the domain model. It separates the product into four focused views:

- `Home` at `/v2`: immediate travel context, next departures, and the highest-value decisions
- `Schedule` at `/v2/schedule`: the complete 26-week trip horizon with lightweight state filters
- `Inbox` at `/v2/inbox`: only bookings, fares, and imports that need user input
- `Rules` at `/v2/rules`: collections and recurring-trip definitions

V2 is not a fork of booking, tracker, or recurrence behavior. It is a new presentation over the same canonical state.

## Coexistence Contract

The following rules are release invariants:

1. `/` and all existing v1 URLs keep their current behavior.
2. There is no redirect from a v1 route to v2.
3. V2 reads through the isolated `/api/v2/workspace` contract.
4. The v2 contract composes existing dashboard/domain services rather than reproducing business rules.
5. Create, edit, booking, and flight-detail actions continue through established v1 flows while v2 is evaluated.
6. The v2 React entry is lazy-loaded. Visiting v1 must not request v2 JavaScript or CSS assets.
7. V2 styles stay under the `v2-*` namespace, apart from the route-scoped `body.v2-route` shell selector.
8. A v2 failure must not prevent v1 from rendering or operating.

## Data Contract

`GET /api/v2/workspace` returns a read model containing:

- the current date and configured recurring horizon
- decision, departure, booking, and tracking counts
- action items produced by the canonical dashboard rules
- all upcoming trips, including skipped trips, with a derived `planning`, `booked`, or `skipped` state
- collection and recurring-rule summaries

Trip rows and action items retain their canonical v1 payload shapes inside the v2 envelope. This keeps links, warnings, booking state, route preference, and fare calculations single-sourced.

## Verification Gates

Every change to the parallel experience must keep these checks green:

```bash
uv run python -m compileall -q app tests scripts
uv run pytest -q
npm --prefix frontend run build
uv run python scripts/playwright_release_smoke.py
```

The browser release smoke verifies:

- the v1 root renders without horizontal overflow or browser errors
- the v1 root does not load v2 assets
- v2 home, schedule, inbox, and rules routes render at desktop width
- v2 home and schedule render at mobile width
- v2 client navigation, schedule filtering, and progressive month disclosure work

CI runs the same compilation, test, build, and browser gates.

## Cutover Criteria

V2 must not become the default route until all of the following are true:

- every daily v1 workflow has an equivalent, verified v2 path
- v2 mutation flows have explicit API contracts and parity tests rather than copied client-side rules
- production use has shown no material data, navigation, accessibility, or mobile regressions
- rollback is a route/config change and does not require a data migration
- the v1 retirement plan identifies compatibility URLs and a bounded support period

Until then, v1 remains the source of operational truth and rollback path.

## Future Architecture

If v2 proves the product direction, evolve it incrementally:

- introduce explicit command endpoints for mutations while retaining domain services as the single source of truth
- add durable outbox/reconciliation boundaries only where external integrations require them
- measure and tune read-model payload size before adding pagination or caching
- retire legacy routes only after behavior parity and observed production stability

Do not add speculative infrastructure solely to make v2 look architecturally independent. Its safety currently comes from sharing canonical state and isolating presentation.
