# Trip Groups And Recurring Rules

## Why This Change Exists

The current `weekly trip` concept is doing too many jobs at once:

- it is the recurring rule
- it is the user-facing grouping container
- it owns route-option templates
- it owns the generated dated trips

That works for routine weekly travel, but it breaks down when a user wants to:

- keep related travel organized together without forcing exact recurrence
- move one occurrence off-pattern, but still keep it with the rest of the series
- manually add a one-off trip into the same portfolio bucket
- stop one generated occurrence from following future rule changes

The product needs two concepts instead of one:

- `Trip Group`: organizational only
- `Recurring Rule`: cadence + template that can create or maintain trips inside a group

## Product Principles

1. A group is just a group.
   It does not imply cadence, route similarity, or ownership rules by itself.

2. A recurring rule is just a rule.
   It decides which trips should exist on a cadence and what template they inherit.

3. Concrete trips remain the operational object.
   Booking, tracking, rebook comparison, and Today-page status stay tied to the concrete dated trip.

4. Users should be able to break a pattern without breaking organization.
   One odd Friday trip should still sit next to the rest of the work-travel series.

5. Generated trips should be detachable.
   If a user wants one occurrence to diverge from the recurring rule, they should be able to detach it and edit it safely.

## Recommended Target Model

### 1. `TripGroup`

New top-level grouping object.

Suggested fields:

- `trip_group_id`
- `label`
- `data_scope`
- timestamps

Semantics:

- pure organizational/display bucket
- a concrete scheduled trip can belong to zero or more groups
- a group can contain any mix of trips
- a group can exist with or without a recurring rule

### 2. `RecurringRule`

New recurring generation object.

Suggested fields:

- `recurring_rule_id`
- `label`
- `active`
- `anchor_weekday`
- `preference_mode`
- `data_scope`
- timestamps

Important design choice:

- rules and groups should be linked through a join table, not a single foreign key
- the data model can support zero or more groups, but the normal UI should require at least one
- a group can receive trips from zero or more rules

### 3. `RecurringRuleRouteOption`

Template route options owned by the recurring rule.

Do **not** reuse concrete `RouteOption` for this.
Template route options and concrete trip route options have different semantics.

Suggested fields mirror the current trip route options:

- `recurring_rule_route_option_id`
- `recurring_rule_id`
- `rank`
- `savings_needed_vs_previous`
- `origin_airports`
- `destination_airports`
- `airlines`
- `day_offset`
- `start_time`
- `end_time`
- `fare_class_policy`
- `data_scope`
- timestamps

### 4. `Trip`

`Trip` should become the concrete dated trip parent, not the recurring rule.

Suggested shape:

- `trip_id`
- `label`
- `generated_by_rule_id` nullable
- `rule_occurrence_date` nullable
- `inheritance_mode`
  - `manual`
  - `attached`
  - `detached`
- `preference_mode`
- `active`
- `anchor_date`
- `data_scope`
- timestamps

Key meaning:

- every concrete trip has one actual operating date
- some concrete trips are rule-generated
- some rule-generated trips are still attached to the rule template
- some have been detached and can diverge
- group membership is owned by the concrete scheduled trip, not inferred only from the rule

### 5. `RouteOption`

Concrete trip route options stay attached to concrete `Trip`.

This is important for detach semantics:

- attached trips can be resynced from the rule template
- detached trips keep their copied route options and diverge safely

### 6. `TripInstance`

Keep this for now.

Near-term role:

- operational unit for bookings, trackers, fetch targets, Today-page status

Long-term note:

- once every concrete trip is one dated trip, `TripInstance` may eventually become redundant
- do **not** collapse it in the same feature

## Lifecycle Semantics

### Creating A Group

Users can create an empty group with no rule.

This supports:

- grouping ad hoc travel
- future rule creation
- manual curation

### Creating A Recurring Rule

Users create a recurring rule and optionally route it into one or more groups.

The rule defines:

- weekday cadence
- preference mode
- template route options

### Generating Concrete Trips

The rule should create or maintain concrete trips and apply its current target groups to attached occurrences.

Occurrence identity should be keyed by:

- `generated_by_rule_id`
- `rule_occurrence_date`

That lets one occurrence remain claimed by the rule even if its actual trip date changes later.

### Attached Trips

An attached generated trip:

- remains in the group
- or in the groups targeted by the rule
- continues to inherit rule changes
- should not allow direct editing of rule-owned fields

Rule-owned fields:

- label derived from the rule
- preference mode
- route options

Operational fields remain per-trip:

- bookings
- current tracker/fetch state

### Detached Trips

Detaching a generated trip should:

- keep its current group memberships
- keep the `generated_by_rule_id` and `rule_occurrence_date`
- switch `inheritance_mode` to `detached`
- stop future template sync from the rule

That way:

- the rule will not recreate the original occurrence
- the user can edit the trip date, label, and route options freely
- the trip still retains lineage for display/history

### Deleting A Generated Trip

Delete should behave like it does today for one-time trips:

- hide it from the product
- keep a tombstone in storage

For rule-generated trips, deletion must also suppress regeneration.

The easiest way to do that is:

- keep the concrete trip row
- set `active = false`
- preserve `generated_by_rule_id` and `rule_occurrence_date`

That row continues to claim the occurrence, so the rule does not regenerate it until a manual restore in the backend.

### Deleting One Occurrence

Deleting an attached occurrence should suppress regeneration for that rule/date without forcing a detach first.

## How Rule Edits Should Propagate

Rule edits should update **future attached trips**, not everything forever.

That includes:

- cadence
- preference mode
- route options
- target groups

Recommended propagation target:

- attached trips
- active
- with `anchor_date >= today`

This avoids rewriting historical or already-booked trips.

Why:

- a booked or past trip is now part of history
- changing the rule later should not silently rewrite what that occurrence meant

If a user wants a future occurrence to stop following the rule, they detach it first.

## Recommended Information Architecture

### `Today`

Keep instance-first.

It should show:

- open concrete trips
- booked concrete trips
- unmatched bookings

It can show group/rule context as secondary copy only.

### `Trips`

This should become the list of concrete scheduled trips.

It should support:

- group filtering
- status filtering
- search

The current recurring-plan cards should move off this page.

### `Groups`

New top-level page.

This is the new home for:

- group list
- group detail
- recurring-rule management

Each group detail page should show:

- group summary
- recurring rules in the group
- upcoming trips in the group
- manual trips in the group

### `Recurring Rule Detail`

Separate rule-editing surface.

It should own:

- cadence
- preference mode
- template route options
- upcoming occurrences created from the rule

### `Trip Detail`

Concrete trip detail remains the operational screen.

For a rule-generated attached trip, it should show:

- group
- recurring rule
- `Detach from rule`

For a detached trip, it should show:

- group
- derived-from-rule lineage
- no live inheritance

## Why We Should Not Do A Big-Bang Rewrite

The current system has strong identity assumptions:

- `TripInstance` identity is based on `(trip_id, anchor_date)`
- tracker IDs are derived from `trip_instance_id`
- fetch-target IDs are derived from tracker IDs
- bookings link to `trip_instance_id`
- unmatched booking candidates store `trip_instance_id`

If we immediately rewrite generated occurrences into brand new parent identities, we risk breaking:

- booking links
- tracker continuity
- fetch-target reuse
- rebook comparisons
- Today-page status continuity

This feature needs a phased rollout.

## Recommended Implementation Phases

### Phase 1: Add Groups

Goal:

- unlock organization first
- minimal operational risk

Work:

- add `TripGroup`
- allow one-time trips to be assigned to a group
- show grouped trips in the UI
- keep current weekly-trip generation as-is temporarily

Result:

- users can already group irregular one-off trips
- low migration risk

### Phase 2: Introduce RecurringRule

Goal:

- split cadence/template from grouping

Work:

- add `RecurringRule`
- migrate existing weekly-trip metadata into rules
- add `RecurringRuleRouteOption`
- keep current weekly trip rows as compatibility shims during rollout if needed

Result:

- recurring logic no longer lives conceptually inside the group

### Phase 3: Generate Concrete Trips Into Groups

Goal:

- make recurring output real, groupable, detachable trips

Work:

- generate concrete trips from rules
- add:
  - `generated_by_rule_id`
  - `rule_occurrence_date`
  - `inheritance_mode`
- keep `TripInstance`/booking/tracker layers stable underneath

Result:

- one odd Friday trip can live in the work-travel group
- it can be detached and edited without breaking the rest of the series

### Phase 4: Remove Legacy Weekly Trip Semantics

Goal:

- complete the model cleanup

Work:

- stop treating `TripKind.WEEKLY` as a real authored product concept
- make `Trip` fully concrete-only
- route recurring UI entirely through groups + rules

Result:

- the model matches the product language

## First Slice I Recommend Building

Do **not** start with detach.

Start with:

1. `TripGroup` model and UI
2. assign existing one-time trips to groups
3. show grouped concrete trips on the Trips page
4. add `RecurringRule` model behind the current weekly-trip UI

Why this first:

- it gives immediate product value
- it establishes the clean grouping concept
- it does not force tracker/booking identity migration yet

Then build detach and rule-generated concrete trips on top of that foundation.

## Summary

The right product direction is:

- `Trip Group` for organization
- `Recurring Rule` for cadence and templates
- concrete `Trip` for the actual travel object

The right engineering direction is:

- do this in phases
- preserve existing `TripInstance`/tracker/booking identity as long as possible
- only move generated trips into full concrete-trip ownership once the group/rule foundation is in place
