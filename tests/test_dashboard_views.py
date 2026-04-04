from __future__ import annotations

from app.models.base import AppState
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.services.dashboard import trip_row_summary
from app.services.snapshots import AppSnapshot


def test_unbooked_trip_row_uses_exact_winning_fetch_target_route_and_airline() -> None:
    snapshot = AppSnapshot(
        trip_groups=[],
        trips=[
            Trip(
                trip_id="trip_1",
                label="Work commute",
                trip_kind="one_time",
                anchor_date="2026-04-06",
            )
        ],
        rule_group_targets=[],
        route_options=[],
        trip_instances=[
            TripInstance(
                trip_instance_id="inst_1",
                trip_id="trip_1",
                display_label="Work commute (2026-04-06)",
                anchor_date="2026-04-06",
            )
        ],
        trip_instance_group_memberships=[],
        trackers=[
            Tracker(
                tracker_id="tracker_1",
                trip_instance_id="inst_1",
                route_option_id="opt_1",
                rank=1,
                preference_bias_dollars=0,
                origin_airports="LAX|BUR",
                destination_airports="SFO",
                airlines="Southwest|Delta",
                day_offset=0,
                travel_date="2026-04-06",
                start_time="06:00",
                end_time="10:00",
                latest_observed_price=88,
                latest_winning_origin_airport="BUR",
                latest_winning_destination_airport="SFO",
            )
        ],
        tracker_fetch_targets=[
            TrackerFetchTarget(
                fetch_target_id="fetch_1",
                tracker_id="tracker_1",
                trip_instance_id="inst_1",
                origin_airport="BUR",
                destination_airport="SFO",
                google_flights_url="https://example.com/gf",
                latest_price=88,
                latest_airline="Southwest",
            )
        ],
        bookings=[],
        unmatched_bookings=[],
        booking_email_events=[],
        price_records=[],
        app_state=AppState(),
    )

    row = trip_row_summary(snapshot, "inst_1")

    assert row["title"] == "Work commute"
    assert row["detail_line"] == "BUR → SFO · Southwest"
    assert {"label": "Best $88", "tone": "success", "href": "https://example.com/gf"} in row["fact_chips"]
