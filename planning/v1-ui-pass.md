## V1 UI/Product Pass

Historical note: this doc captures the first major UI consolidation pass. It is useful for intent, but some references below still predate the current group/rule model and the removal of the user-facing skip state.

### Product framing
- `Today` is the action inbox.
- `Trips` is the planning workspace.
- `Bookings` is the ledger of purchased travel.
- unmatched bookings are managed inline on `Bookings`, not through a separate primary page.
- Global tracker browsing is removed. Tracker detail lives under a scheduled trip instance.

### Core surfaces

#### Today
- Lead with items that need action now:
  - unmatched bookings
  - open trips with `book_now`
  - booked trips with `rebook`
- Keep secondary sections for:
  - open trips still being watched
  - booked trips still being monitored

#### Trips
- Keep recurring trips as the parent planning construct.
- Add a real trip detail page at `/trips/{trip_id}`.
- Scheduled trip rows should focus on operational actions for one dated trip instance:
  - open trip
  - record booking
  - delete occurrence or delete trip

#### Trip detail
- Parent trip page should show:
  - trip summary and controls
  - ranked route options
  - whether route options are treated equally or in ranked order
  - any configured savings thresholds that lower-ranked options must clear
  - dated trip instances generated from the trip

#### Scheduled trip detail
- Scheduled trip page should replace the old "tracker-only" mental model.
- It should include:
  - trip/date summary
  - booking state
  - tracker cards for that dated trip
  - refresh sooner
  - delete occurrence or delete trip
  - quick links to sibling dates in the same recurring series

#### Bookings
- Avoid raw internal ids in the UI.
- Show booking context in travel terms:
  - trip label
  - date
  - route
  - airline
  - record locator
- keep unmatched actions adjacent to the unresolved booking itself:
  - link to an existing trip instance
  - create a new one-time trip from the booking

### UX cleanups
- Flash feedback should remain transient toast-based.
- Reuse the improved route-option picker; avoid adding new picker variants unless they clearly help.
- Keep route-option preference controls simple:
  - equal treatment by default
  - optional ranked-order mode with dollar savings thresholds
- Prefer denser but calmer cards over large repetitive status badges.
- Use one primary action per card and demote secondary actions where possible.

### Non-goals for this pass
- Database migration
- Historical analytics UI
- Past-trip management UI
- a separate inbox-resolution workspace
