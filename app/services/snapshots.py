from __future__ import annotations

from dataclasses import dataclass

from app.models.booking import Booking
from app.models.booking_email_event import BookingEmailEvent
from app.models.price_record import PriceRecord
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_group import TripGroup
from app.models.trip_instance import TripInstance
from app.models.trip_instance_group_membership import TripInstanceGroupMembership
from app.models.rule_group_target import RuleGroupTarget


@dataclass
class AppSnapshot:
    trip_groups: list[TripGroup]
    trips: list[Trip]
    rule_group_targets: list[RuleGroupTarget]
    route_options: list[RouteOption]
    trip_instances: list[TripInstance]
    trip_instance_group_memberships: list[TripInstanceGroupMembership]
    trackers: list[Tracker]
    tracker_fetch_targets: list[TrackerFetchTarget]
    bookings: list[Booking]
    unmatched_bookings: list[Booking]
    booking_email_events: list[BookingEmailEvent]
    price_records: list[PriceRecord]
    app_state: object
