from __future__ import annotations

from datetime import timedelta

from app.models.base import AppState
from app.models.base import utcnow
from app.models.booking import Booking
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.services.scheduled_trip_display import trip_row_summary
from app.services.snapshots import AppSnapshot


def test_unbooked_trip_row_uses_exact_winning_fetch_target_route_and_airline() -> None:
    fresh_at = utcnow() - timedelta(hours=1)
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
                latest_fetched_at=fresh_at,
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
                latest_departure_label="6:35 AM on Mon, Apr 6",
                latest_fetched_at=fresh_at,
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
    assert row["booked_offer"] is None
    assert row["current_offer"] == {
        "label": "Live fare",
        "detail": "BUR → SFO",
        "airline_key": "Southwest",
        "primary_meta_label": "6:35 AM",
        "meta_badges": [],
        "meta_label": "6:35 AM",
        "price_label": "$88",
        "href": "https://example.com/gf",
        "tone": "success",
        "price_is_status": False,
    }


def test_unbooked_trip_row_fallback_route_spaces_multi_airport_options() -> None:
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
                destination_airports="SFO|OAK",
                airlines="Southwest",
                day_offset=0,
                travel_date="2026-04-06",
                start_time="06:00",
                end_time="10:00",
                latest_observed_price=None,
            )
        ],
        tracker_fetch_targets=[],
        bookings=[],
        unmatched_bookings=[],
        booking_email_events=[],
        price_records=[],
        app_state=AppState(),
    )

    row = trip_row_summary(snapshot, "inst_1")

    assert row["current_offer"] == {
        "label": "Live fare",
        "detail": "LAX | BUR → SFO | OAK",
        "airline_key": "Southwest",
        "primary_meta_label": "",
        "meta_badges": [],
        "meta_label": "",
        "price_label": "Checking",
        "href": "",
        "tone": "neutral",
        "price_is_status": True,
        "status_kind": "pending",
    }


def test_unbooked_trip_row_hides_stale_tracker_price() -> None:
    stale_at = utcnow() - timedelta(hours=80)
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
                destination_airports="SFO|OAK",
                airlines="Southwest",
                day_offset=0,
                travel_date="2026-04-06",
                start_time="06:00",
                end_time="10:00",
                latest_observed_price=88,
                latest_fetched_at=stale_at,
            )
        ],
        tracker_fetch_targets=[
            TrackerFetchTarget(
                fetch_target_id="fetch_1",
                tracker_id="tracker_1",
                trip_instance_id="inst_1",
                origin_airport="LAX",
                destination_airport="SFO",
                google_flights_url="https://example.com/gf",
                latest_price=88,
                latest_departure_label="6:35 AM",
                latest_fetched_at=stale_at,
            )
        ],
        bookings=[],
        unmatched_bookings=[],
        booking_email_events=[],
        price_records=[],
        app_state=AppState(),
    )

    row = trip_row_summary(snapshot, "inst_1")

    assert row["current_offer"] == {
        "label": "Live fare",
        "detail": "LAX | BUR → SFO | OAK",
        "airline_key": "Southwest",
        "primary_meta_label": "",
        "meta_badges": [],
        "meta_label": "",
        "price_label": "Checking",
        "href": "",
        "tone": "neutral",
        "price_is_status": True,
        "status_kind": "pending",
    }


def test_unbooked_trip_row_shows_na_when_all_trackers_have_no_results() -> None:
    fresh_at = utcnow() - timedelta(hours=1)
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
                origin_airports="BUR",
                destination_airports="SFO",
                airlines="Alaska",
                day_offset=0,
                travel_date="2026-04-06",
                start_time="06:00",
                end_time="10:00",
                latest_observed_price=None,
                latest_fetched_at=fresh_at,
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
                last_fetch_status="no_results",
                last_fetch_finished_at=fresh_at,
                latest_price=None,
                latest_fetched_at=fresh_at,
            )
        ],
        bookings=[],
        unmatched_bookings=[],
        booking_email_events=[],
        price_records=[],
        app_state=AppState(),
    )

    row = trip_row_summary(snapshot, "inst_1")

    assert row["current_offer"] == {
        "label": "Live fare",
        "detail": "BUR → SFO",
        "airline_key": "Alaska",
        "primary_meta_label": "",
        "meta_badges": [],
        "meta_label": "",
        "price_label": "N/A",
        "href": "",
        "tone": "neutral",
        "price_is_status": True,
        "status_kind": "unavailable",
    }


def test_booked_trip_row_shows_booked_and_current_best_itineraries() -> None:
    fresh_at = utcnow() - timedelta(hours=1)
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
                latest_fetched_at=fresh_at,
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
                latest_fetched_at=fresh_at,
            )
        ],
        bookings=[
            Booking(
                booking_id="book_1",
                trip_instance_id="inst_1",
                route_option_id="opt_1",
                airline="Delta",
                origin_airport="LAX",
                destination_airport="SFO",
                departure_date="2026-04-06",
                departure_time="08:15",
                arrival_time="09:45",
                flight_number="2285",
                booked_price=124,
            )
        ],
        unmatched_bookings=[],
        booking_email_events=[],
        price_records=[],
        app_state=AppState(),
    )

    row = trip_row_summary(snapshot, "inst_1")

    assert row["booked_offer"] == {
        "label": "Booked",
        "detail": "LAX → SFO",
        "airline_key": "Delta",
        "primary_meta_label": "8:15 AM → 9:45 AM · DL 2285",
        "meta_badges": [],
        "meta_label": "8:15 AM → 9:45 AM · DL 2285",
        "price_label": "$124",
        "href": "",
        "tone": "neutral",
        "price_is_status": False,
    }
    assert row["current_offer"] == {
        "label": "Live fare",
        "detail": "BUR → SFO",
        "airline_key": "Southwest",
        "primary_meta_label": "",
        "meta_badges": [],
        "meta_label": "",
        "price_label": "$88",
        "href": "https://example.com/gf",
        "tone": "accent",
        "price_is_status": False,
    }


def test_trip_row_shows_departure_time_and_day_shift_when_itinerary_moves_off_anchor_date() -> None:
    fresh_at = utcnow() - timedelta(hours=1)
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
                day_offset=1,
                travel_date="2026-04-07",
                start_time="06:00",
                end_time="10:00",
                latest_observed_price=88,
                latest_fetched_at=fresh_at,
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
                latest_departure_label="6:10 AM",
                latest_fetched_at=fresh_at,
            )
        ],
        bookings=[
            Booking(
                booking_id="book_1",
                trip_instance_id="inst_1",
                route_option_id="",
                airline="Delta",
                origin_airport="LAX",
                destination_airport="SFO",
                departure_date="2026-04-05",
                departure_time="23:30",
                arrival_time="01:10",
                arrival_day_offset=1,
                flight_number="2285",
                booked_price=124,
            )
        ],
        unmatched_bookings=[],
        booking_email_events=[],
        price_records=[],
        app_state=AppState(),
    )

    row = trip_row_summary(snapshot, "inst_1")

    assert row["booked_offer"] == {
        "label": "Booked",
        "detail": "LAX → SFO",
        "airline_key": "Delta",
        "primary_meta_label": "11:30 PM⁻¹ → 1:10 AM · DL 2285",
        "meta_badges": [],
        "meta_label": "11:30 PM⁻¹ → 1:10 AM · DL 2285",
        "price_label": "$124",
        "href": "",
        "tone": "neutral",
        "price_is_status": False,
    }
    assert row["current_offer"] == {
        "label": "Live fare",
        "detail": "BUR → SFO",
        "airline_key": "Southwest",
        "primary_meta_label": "6:10 AM⁺¹",
        "meta_badges": [],
        "meta_label": "6:10 AM⁺¹",
        "price_label": "$88",
        "href": "https://example.com/gf",
        "tone": "accent",
        "price_is_status": False,
    }


def test_trip_row_shows_multi_leg_booking_numbers_and_stop_label() -> None:
    snapshot = AppSnapshot(
        trip_groups=[],
        trips=[
            Trip(
                trip_id="trip_1",
                label="Return home",
                trip_kind="one_time",
                anchor_date="2026-06-01",
            )
        ],
        rule_group_targets=[],
        route_options=[],
        trip_instances=[
            TripInstance(
                trip_instance_id="inst_1",
                trip_id="trip_1",
                display_label="Return home (2026-06-01)",
                anchor_date="2026-06-01",
            )
        ],
        trip_instance_group_memberships=[],
        trackers=[],
        tracker_fetch_targets=[],
        bookings=[
            Booking(
                booking_id="book_1",
                trip_instance_id="inst_1",
                route_option_id="",
                airline="Alaska",
                origin_airport="SEA",
                destination_airport="BUR",
                departure_date="2026-06-01",
                departure_time="11:12",
                arrival_time="19:34",
                stops="1_stop",
                flight_number="1484 | 530",
                booked_price=0,
            )
        ],
        unmatched_bookings=[],
        booking_email_events=[],
        price_records=[],
        app_state=AppState(),
    )

    row = trip_row_summary(snapshot, "inst_1")

    assert row["booked_offer"] == {
        "label": "Booked",
        "detail": "SEA → BUR · 1 stop",
        "airline_key": "Alaska",
        "primary_meta_label": "11:12 AM → 7:34 PM · AS 1484 · AS 530",
        "meta_badges": [],
        "meta_label": "11:12 AM → 7:34 PM · AS 1484 · AS 530",
        "price_label": "$0",
        "href": "",
        "tone": "neutral",
        "price_is_status": False,
    }


def test_trip_row_stacks_explicit_arrival_day_shift_on_top_of_travel_day_offset() -> None:
    fresh_at = utcnow() - timedelta(hours=1)
    snapshot = AppSnapshot(
        trip_groups=[],
        trips=[
            Trip(
                trip_id="trip_1",
                label="Overnight hop",
                trip_kind="one_time",
                anchor_date="2026-04-20",
            )
        ],
        rule_group_targets=[],
        route_options=[],
        trip_instances=[
            TripInstance(
                trip_instance_id="inst_1",
                trip_id="trip_1",
                display_label="Overnight hop (2026-04-20)",
                anchor_date="2026-04-20",
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
                origin_airports="SFO",
                destination_airports="LAX",
                airlines="Southwest",
                day_offset=1,
                travel_date="2026-04-21",
                start_time="16:00",
                end_time="22:00",
                latest_observed_price=109,
                latest_fetched_at=fresh_at,
                latest_winning_origin_airport="SFO",
                latest_winning_destination_airport="LAX",
            )
        ],
        tracker_fetch_targets=[
            TrackerFetchTarget(
                fetch_target_id="fetch_1",
                tracker_id="tracker_1",
                trip_instance_id="inst_1",
                origin_airport="SFO",
                destination_airport="LAX",
                google_flights_url="https://example.com/gf",
                latest_price=109,
                latest_airline="Southwest",
                latest_departure_label="8:10 PM on Thu, Apr 21",
                latest_arrival_label="9:40 PM on Fri, Apr 22",
                latest_fetched_at=fresh_at,
            )
        ],
        bookings=[],
        unmatched_bookings=[],
        booking_email_events=[],
        price_records=[],
        app_state=AppState(),
    )

    row = trip_row_summary(snapshot, "inst_1")

    assert row["current_offer"] == {
        "label": "Live fare",
        "detail": "SFO → LAX",
        "airline_key": "Southwest",
        "primary_meta_label": "8:10 PM⁺¹ → 9:40 PM⁺²",
        "meta_badges": [],
        "meta_label": "8:10 PM⁺¹ → 9:40 PM⁺²",
        "price_label": "$109",
        "href": "https://example.com/gf",
        "tone": "success",
        "price_is_status": False,
    }
