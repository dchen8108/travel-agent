# travel-agent v0 Wireframes

## Design Baseline

The MVP is trips-first.

The user should think in this order:

1. `Trip`
2. `Route Option`
3. `Trip Instance`
4. `Booking`
5. `Tracker`

Trackers are visible, but they should not dominate the information architecture.

## 1. Today

```text
+--------------------------------------------------------------+
| travel-agent                                Import | Booking |
+--------------------------------------------------------------+
| Open trips: 9 | Booked: 3 | Resolve: 1                       |
+--------------------------------------------------------------+

Open trips
+--------------------------------------------------------------+
| LA to SF Outbound (2026-04-06)                              |
| Latest signal: $118 on Alaska from BUR -> SFO               |
| State: wait                                                 |
| [Open in trips] [Record booking]                            |
+--------------------------------------------------------------+

Booked trips
+--------------------------------------------------------------+
| SF to LA Return (2026-04-08)                                |
| Booked at $129 | Latest matched signal $109                 |
| State: rebook                                               |
| [Open in trips] [Bookings]                                  |
+--------------------------------------------------------------+
```

## 2. Trips

```text
+--------------------------------------------------------------+
| Trips                                            [New trip] |
+--------------------------------------------------------------+
| Recurring trips                                              |
| LA to SF Outbound | weekly | active                         |
| Route options: 2 | Next instance: 2026-04-06               |
| [Show scheduled] [Edit] [Pause]                            |
+--------------------------------------------------------------+
| Scheduled trips                                              |
| Search trips: [ LA to SF                       ]            |
| Recurring trips: [ Weekly commute x ] [ search ... ]       |
| [Show skipped toggle]                         [Clear filters]|
| Conference Arrival (2026-05-10) | standalone               |
| [Edit trip] [Record booking] [Skip]                        |
+--------------------------------------------------------------+
```

## 3. Trip Form

```text
Trip label: [ LA to SF Outbound                        ]
Trip kind:  ( ) One-time   ( ) Weekly

If one-time:
Anchor date: [ 2026-05-10 ]

If weekly:
Anchor weekday: [ Monday v ]

Route options
+--------------------------------------------------------------+
| Origins        [ BUR      x ] [ LAX      x ] [ search ... ] |
| Destinations   [ SFO      x ] [ search ... ]                |
| Airlines       [ Alaska   x ] [ United   x ] [ search ... ] |
| Relative day   [ Monday (T) v ]                             |
| Time window    [ 06:00 ] to [ 10:00 ]                       |
| [Remove option]                                             |
+--------------------------------------------------------------+

[Add route option]
[Save trip]
```

## 4. Bookings

```text
+--------------------------------------------------------------+
| Bookings                                       [Add booking] |
+--------------------------------------------------------------+
| LA to SF Outbound (2026-04-06)                              |
| Alaska | BUR -> SFO | 07:10 -> 08:31 | $129                 |
| Attached to tracker option 1                                |
| [Open in trips]                                             |
+--------------------------------------------------------------+
```

## 5. Resolve

```text
+--------------------------------------------------------------+
| Resolve unmatched bookings                                  |
+--------------------------------------------------------------+
| Record locator: ABC123                                      |
| Alaska | BUR -> SFO | 2026-04-06 07:10                      |
| Could not match confidently                                 |
| Link to trip instance: [ LA to SF Outbound (2026-04-06) v ] |
| [Link booking] [Create one-time trip]                       |
+--------------------------------------------------------------+
```

## 6. Trackers

```text
+--------------------------------------------------------------+
| Trackers                                                     |
+--------------------------------------------------------------+
| LA to SF Outbound (2026-04-06)                              |
| Option 1 | BUR,LAX -> SFO | Monday (T) | 06:00-10:00        |
| Status: signal_received | Latest: $118                      |
| [Open Google Flights] [Paste link] [Mark enabled]           |
|                                                              |
| Option 2 | BUR -> SFO | Sunday (T-1) | 18:00-21:00          |
| Status: needs_setup                                          |
| [Open Google Flights] [Paste link] [Mark enabled]           |
+--------------------------------------------------------------+
```
