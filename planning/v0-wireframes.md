# travel-agent v0 Wireframes

These are intentionally low-fidelity. They define layout, information order, and action hierarchy rather than visual design.

## 1. Today

```text
+----------------------------------------------------------------------------------+
| travel-agent                                                   Last updated 8:05 |
+----------------------------------------------------------------------------------+
| Today | Trackers | Imports | Review | Rules | Add Booking                       |
+----------------------------------------------------------------------------------+
| 1 tracker gap | 1 book now | 1 safe to wait | 1 rebook opportunity              |
+----------------------------------------------------------------------------------+
| NEEDS TRACKER SETUP                                                              |
| -------------------------------------------------------------------------------- |
| BUR -> SFO | Mon May 12 - Wed May 14                                             |
| Outbound tracker missing, return tracker missing               [SETUP NEEDED]    |
| Create both Google Flights segment trackers so this trip can receive signals.    |
| [Open Google Flights] [Paste link] [Mark tracking enabled]                       |
+----------------------------------------------------------------------------------+
| BOOK NOW                                                                         |
| -------------------------------------------------------------------------------- |
| LAX -> SFO | Mon May 19 - Wed May 21                                             |
| Latest Google Flights price: $186 | Signal received 8:02 AM     [BOOK NOW]      |
| Attractive recent fare inside your booking window.                               |
| [View details] [Mark booked]                                                     |
+----------------------------------------------------------------------------------+
| REBOOK OPPORTUNITIES                                                             |
| -------------------------------------------------------------------------------- |
| LAX -> SFO | Mon Jun 2 - Wed Jun 4                                               |
| Booked at $224 | Latest Google Flights price: $181          [REBOOK]             |
| Estimated savings: $43 if you cancel and rebook.                                 |
| [View details] [Mark rebooked]                                                   |
+----------------------------------------------------------------------------------+
| WAIT                                                                             |
| -------------------------------------------------------------------------------- |
| BUR -> SFO | Mon May 26 - Wed May 28                                             |
| Tracking enabled | Last Google Flights update yesterday       [WAIT]             |
| No compelling price movement yet. Continue monitoring.                           |
| [View details] [Dismiss today]                                                   |
+----------------------------------------------------------------------------------+
```

## 2. Trackers

```text
+----------------------------------------------------------------------------------+
| Trackers                                                                        |
+----------------------------------------------------------------------------------+
| Trip                              Status             Last signal    Latest price |
|----------------------------------------------------------------------------------|
| BUR -> SFO | May 12 - May 14      SETUP NEEDED       --             --          |
| [Open Google Flights] [Paste link] [Mark tracking enabled] [View trip]          |
|----------------------------------------------------------------------------------|
| BUR -> SFO | Mon May 19             SIGNAL RECEIVED    Today 8:02 AM  $186      |
| [Open Google Flights] [Upload email] [View trip]                                |
|----------------------------------------------------------------------------------|
| SFO -> BUR | Wed May 21             TRACKING ENABLED   Yesterday      $201      |
| [Open Google Flights] [Upload email] [View trip]                                |
+----------------------------------------------------------------------------------+
```

## 3. Imports / Review

```text
+----------------------------------------------------------------------------------+
| Imports                                                                         |
+----------------------------------------------------------------------------------+
| [Choose .eml] [Import Google Flights email]                                     |
+----------------------------------------------------------------------------------+
| RECENT IMPORTS                                                                  |
| -------------------------------------------------------------------------------- |
| Prices for your tracked flights... | PARSED | 5 observations                     |
| Prices for your tracked flights... | NEEDS REVIEW | 3 observations               |
+----------------------------------------------------------------------------------+
| NEEDS REVIEW                                                                    |
| -------------------------------------------------------------------------------- |
| JFK -> LAX | Tue Jun 30 | American | $269                                       |
| 12:00 PM – 3:21 PM · American · nonstop · JFK–LAX                               |
| [match to tracker ▼] [Ignore]                                                   |
+----------------------------------------------------------------------------------+
```

## 4. Trip Detail: Unbooked

```text
+----------------------------------------------------------------------------------+
| BUR -> SFO | Mon May 19 - Wed May 21                                            |
+----------------------------------------------------------------------------------+
| Tracker coverage: outbound signal received, return tracking enabled             |
| Recommendation: BOOK NOW                                                        |
| Latest observed total: $387 ($186 outbound + $201 return)                       |
| Reason: Segment pricing is acceptable inside your preferred buy window.         |
+----------------------------------------------------------------------------------+
| OUTBOUND SEGMENT                                                                 |
| Source: Google Flights email                                                     |
| Observed at: Apr 4, 8:02 AM                                                      |
| Airline: Alaska                                                                  |
| Fare type: Flexible                                                              |
| Observed price: $186                                                             |
+----------------------------------------------------------------------------------+
| RETURN SEGMENT                                                                   |
| Source: Google Flights email                                                     |
| Observed at: Apr 3, 9:10 AM                                                      |
| Airline: Alaska                                                                  |
| Fare type: Flexible                                                              |
| Observed price: $201                                                             |
+----------------------------------------------------------------------------------+
| RECENT SEGMENT OBSERVATIONS                                                     |
| Outbound Apr 1   $212                                                           |
| Outbound Apr 2   $205                                                           |
| Outbound Apr 4   $186                                                           |
| Return   Apr 3   $201                                                           |
+----------------------------------------------------------------------------------+
| [Open Google Flights] [Mark booked] [Back to Today]                             |
+----------------------------------------------------------------------------------+
```

## 5. Trip Detail: Booked

```text
+----------------------------------------------------------------------------------+
| LAX -> SFO | Mon Jun 2 - Wed Jun 4                                              |
+----------------------------------------------------------------------------------+
| Recommendation: REBOOK                                                          |
| Estimated savings: $43                                                          |
| Reason: Combined latest segment prices are materially below your booked price.  |
+----------------------------------------------------------------------------------+
| BOOKED TRIP                                                                     |
| Airline: United                                                                 |
| Fare type: Flexible                                                             |
| Booked price: $224                                                              |
| Booking date: Apr 3                                                             |
+----------------------------------------------------------------------------------+
| LATEST SEGMENT COMPARISON                                                       |
| Outbound latest: $91                                                            |
| Return latest:   $90                                                            |
| Combined current total: $181                                                    |
| Difference vs booked: -$43                                                      |
+----------------------------------------------------------------------------------+
| RECENT OBSERVATIONS                                                             |
| Apr 8   $224                                                                    |
| Apr 9   $214                                                                    |
| Apr 10  $206                                                                    |
| Apr 11  $181                                                                    |
+----------------------------------------------------------------------------------+
| [Mark rebooked] [Update booking] [Back to Today]                                |
+----------------------------------------------------------------------------------+
```

## 6. Rules

```text
+----------------------------------------------------------------------------------+
| Rules                                                                           |
+----------------------------------------------------------------------------------+
| Program name: [ LA to SF Weekly Commute                                      ] |
| Origins:      [ BUR, LAX, SNA                                                 ] |
| Destinations: [ SFO                                                           ] |
| Outbound day: [ Monday ]   Preferred departure window: [ 6 AM - 10 AM        ] |
| Return day:   [ Wednesday ] Preferred departure window: [ 4 PM - 9 PM        ] |
| Preferred airlines: [ Alaska, United, Delta                                  ] |
| Allowed airlines:   [ Alaska, United, Delta, Southwest                       ] |
| Fare preference:    [ Flexible                                               ] |
| Nonstop only:       [ Yes                                                    ] |
| Lookahead window:   [ 8 weeks                                                ] |
| Rebook alert threshold: [ $20                                                ] |
| Email import mode:    [ Manual .eml upload                                   ] |
| [Save rules]                                                                    |
+----------------------------------------------------------------------------------+
```

## 7. Add Booking

```text
+----------------------------------------------------------------------------------+
| Add Booking                                                                     |
+----------------------------------------------------------------------------------+
| Trip instance: [ Mon Jun 2 - Wed Jun 4 | LAX -> SFO                          ] |
| Airline:       [ United                                                      ] |
| Fare type:     [ Flexible                                                   ] |
| Booked price:  [ 224                                                        ] |
| Booking date:  [ 2026-04-03                                                 ] |
| Record locator:[ ABC123                                                     ] |
| Notes:                                                                           |
| [ I booked through the United app after a fare alert.                          ] |
|                                                                                  |
| Alternate input: Paste itinerary text                                           |
| [                                                                              ] |
| [Save booking]                                                                   |
+----------------------------------------------------------------------------------+
```

## Card States

### `needs_tracker_setup`

- badge text: `SETUP NEEDED`
- color intent: blocked / neutral-warning
- price shown: none
- CTA: `Open Google Flights`

### `book_now`

- badge text: `BOOK NOW`
- color intent: positive / high-priority
- price shown: latest observed fare
- CTA: `Mark booked`

### `wait`

- badge text: `WAIT`
- color intent: neutral
- price shown: latest observed fare if available
- CTA: `Dismiss today`

### `booked_monitoring`

- badge text: `BOOKED`
- color intent: stable / informational
- price shown: booked price and latest comparable fare when available
- CTA: `View details`

### `rebook`

- badge text: `REBOOK`
- color intent: warning / high-priority
- price shown: booked price and latest comparable fare
- CTA: `Mark rebooked`

## Deferred: Email Digest Wireframe

```text
Subject: travel-agent daily digest: 1 tracker, 1 action, 1 rebook

You have 3 notable updates today.

TRACKER SETUP
- BUR -> SFO | May 12 - May 14
  Google Flights tracking is not enabled yet for this trip.

BOOK NOW
- LAX -> SFO | May 19 - May 21 | latest observed $186
  Recent Google Flights signal shows an attractive fare inside your booking window.

REBOOK
- LAX -> SFO | Jun 2 - Jun 4 | booked $224, now $181
  Estimated savings: $43.

Open dashboard: http://localhost:3000
```
