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
| Needs setup: 4 | Open trips: 9 | Booked: 3 | Resolve: 1      |
+--------------------------------------------------------------+

Needs setup
+--------------------------------------------------------------+
| LA to SF Outbound (2026-04-06)                              |
| 2 route options | 0/2 trackers enabled                      |
| Needs tracker setup before recommendations become useful    |
| [View trip] [Trackers]                                      |
+--------------------------------------------------------------+

Open trips
+--------------------------------------------------------------+
| LA to SF Outbound (2026-04-06)                              |
| Latest signal: $118 on Alaska from BUR -> SFO               |
| State: wait                                                 |
| [View details] [Record booking]                             |
+--------------------------------------------------------------+

Booked trips
+--------------------------------------------------------------+
| SF to LA Return (2026-04-08)                                |
| Booked at $129 | Latest matched signal $109                 |
| State: rebook                                               |
| [View details] [Update booking]                             |
+--------------------------------------------------------------+
```

## 2. Trips

```text
+--------------------------------------------------------------+
| Trips                                            [New trip] |
+--------------------------------------------------------------+
| LA to SF Outbound | weekly | active                         |
| Route options: 2 | Next instance: 2026-04-06               |
| [View] [Edit] [Pause] [Delete]                             |
+--------------------------------------------------------------+
| Conference Arrival | one_time | active                      |
| Route options: 1 | Instance: 2026-05-10                    |
| [View] [Edit] [Delete]                                     |
+--------------------------------------------------------------+
```

## 3. Trip Detail

```text
+--------------------------------------------------------------+
| LA to SF Outbound                                [Edit trip] |
| Weekly | Anchor weekday: Monday | Active                    |
+--------------------------------------------------------------+

Route options
1. BUR, LAX -> SFO | Alaska, United | Monday (T) | 06:00-10:00
   [Move up] [Move down] [Delete]

2. BUR -> SFO | Alaska | Sunday (T-1) | 18:00-21:00
   [Move up] [Move down] [Delete]

Upcoming instances
+--------------------------------------------------------------+
| 2026-04-06 | open    | wait                 | [View] [Skip] |
| 2026-04-13 | booked  | booked_monitoring    | [View]        |
| 2026-04-20 | skipped | needs_tracker_setup  | [Restore]     |
+--------------------------------------------------------------+
```

## 4. Trip Form

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

## 5. Bookings

```text
+--------------------------------------------------------------+
| Bookings                                       [Add booking] |
+--------------------------------------------------------------+
| LA to SF Outbound (2026-04-06)                              |
| Alaska | BUR -> SFO | 07:10 -> 08:31 | $129                 |
| Attached to tracker option 1                                |
| [View trip]                                                 |
+--------------------------------------------------------------+
```

## 6. Resolve

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

## 7. Trackers

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
