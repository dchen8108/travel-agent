from __future__ import annotations

from datetime import date

from app.models.booking import Booking
from app.services.dashboard import factual_trip_status_label, factual_trip_status_reason, trackers_for_instance
from app.services.recommendations import best_tracker_for_instance, recompute_trip_states
from app.services.trips import save_trip
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


def _single_instance_snapshot(repository: Repository, *, preference_mode: str, payloads: list[dict[str, object]]):
    trip = save_trip(
        repository,
        trip_id=None,
        label="Preference Test Trip",
        trip_kind="one_time",
        anchor_date=date(2026, 4, 6),
        anchor_weekday="",
        active=True,
        preference_mode=preference_mode,
        route_option_payloads=payloads,
    )
    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    instance = next(item for item in snapshot.trip_instances if item.trip_id == trip.trip_id)
    return snapshot, instance, trackers_for_instance(snapshot, instance.trip_instance_id)


def _single_instance_trackers(repository: Repository, *, preference_mode: str, payloads: list[dict[str, object]]):
    _, _, trackers = _single_instance_snapshot(repository, preference_mode=preference_mode, payloads=payloads)
    return trackers


def test_equal_preference_mode_still_picks_cheapest_tracker(repository: Repository) -> None:
    trackers = _single_instance_trackers(
        repository,
        preference_mode="equal",
        payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            },
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "United",
                "day_offset": 0,
                "start_time": "18:00",
                "end_time": "22:00",
                "savings_needed_vs_previous": 80,
            },
        ],
    )

    trackers[0].latest_observed_price = 180
    trackers[1].latest_observed_price = 150

    winner = best_tracker_for_instance(trackers)

    assert winner is not None
    assert winner.rank == 2
    assert trackers[0].preference_bias_dollars == 0
    assert trackers[1].preference_bias_dollars == 0


def test_ranked_bias_requires_lower_option_to_clear_threshold(repository: Repository) -> None:
    trackers = _single_instance_trackers(
        repository,
        preference_mode="ranked_bias",
        payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            },
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "United",
                "day_offset": 0,
                "start_time": "18:00",
                "end_time": "22:00",
                "savings_needed_vs_previous": 50,
            },
        ],
    )

    trackers[0].latest_observed_price = 180
    trackers[1].latest_observed_price = 150

    winner = best_tracker_for_instance(trackers)

    assert winner is not None
    assert winner.rank == 1
    assert trackers[1].preference_bias_dollars == 50

    trackers[1].latest_observed_price = 131
    winner = best_tracker_for_instance(trackers)

    assert winner is not None
    assert winner.rank == 1

    trackers[1].latest_observed_price = 130
    winner = best_tracker_for_instance(trackers)

    assert winner is not None
    assert winner.rank == 2


def test_ranked_bias_accumulates_across_multiple_options(repository: Repository) -> None:
    trackers = _single_instance_trackers(
        repository,
        preference_mode="ranked_bias",
        payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            },
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "United",
                "day_offset": 0,
                "start_time": "08:00",
                "end_time": "11:00",
                "savings_needed_vs_previous": 30,
            },
            {
                "origin_airports": "SNA",
                "destination_airports": "SFO",
                "airlines": "Southwest",
                "day_offset": 0,
                "start_time": "17:00",
                "end_time": "21:00",
                "savings_needed_vs_previous": 20,
            },
        ],
    )

    assert [tracker.preference_bias_dollars for tracker in trackers] == [0, 30, 50]

    trackers[0].latest_observed_price = 200
    trackers[1].latest_observed_price = 172
    trackers[2].latest_observed_price = 151

    winner = best_tracker_for_instance(trackers)
    assert winner is not None
    assert winner.rank == 1

    trackers[2].latest_observed_price = 150
    winner = best_tracker_for_instance(trackers)
    assert winner is not None
    assert winner.rank == 3


def test_first_route_option_threshold_is_forced_to_zero(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Bias Reset Trip",
        trip_kind="one_time",
        anchor_date=date(2026, 4, 6),
        anchor_weekday="",
        active=True,
        preference_mode="ranked_bias",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
                "savings_needed_vs_previous": 999,
            }
        ],
    )

    option = next(item for item in repository.load_route_options() if item.trip_id == trip.trip_id)
    assert option.savings_needed_vs_previous == 0


def test_missing_top_option_price_does_not_block_lower_ranked_winner(repository: Repository) -> None:
    trackers = _single_instance_trackers(
        repository,
        preference_mode="ranked_bias",
        payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            },
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "United",
                "day_offset": 0,
                "start_time": "18:00",
                "end_time": "22:00",
                "savings_needed_vs_previous": 50,
            },
        ],
    )

    trackers[0].latest_observed_price = None
    trackers[1].latest_observed_price = 180

    winner = best_tracker_for_instance(trackers)

    assert winner is not None
    assert winner.rank == 2


def test_weighted_winner_drives_open_trip_status_reason(repository: Repository) -> None:
    snapshot, instance, trackers = _single_instance_snapshot(
        repository,
        preference_mode="ranked_bias",
        payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            },
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "United",
                "day_offset": 0,
                "start_time": "18:00",
                "end_time": "22:00",
                "savings_needed_vs_previous": 50,
            },
        ],
    )

    trackers[0].latest_observed_price = 180
    trackers[1].latest_observed_price = 130

    recompute_trip_states(snapshot.trip_instances, trackers, [])

    refreshed = next(item for item in snapshot.trip_instances if item.trip_instance_id == instance.trip_instance_id)
    assert factual_trip_status_label(snapshot, refreshed.trip_instance_id) == "Planned"
    reason = factual_trip_status_reason(snapshot, refreshed.trip_instance_id)
    assert "option 2" in reason.lower()
    assert "$50 preference buffer" in reason


def test_open_trip_stays_fetching_until_all_route_options_settle(repository: Repository) -> None:
    snapshot, instance, trackers = _single_instance_snapshot(
        repository,
        preference_mode="equal",
        payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            },
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "United",
                "day_offset": 0,
                "start_time": "18:00",
                "end_time": "22:00",
            },
        ],
    )

    trackers[0].latest_observed_price = 180
    trackers[1].latest_observed_price = None

    recompute_trip_states(snapshot.trip_instances, trackers, [])

    refreshed = next(item for item in snapshot.trip_instances if item.trip_instance_id == instance.trip_instance_id)
    assert factual_trip_status_label(snapshot, refreshed.trip_instance_id) == "Fetching prices"
    reason = factual_trip_status_reason(snapshot, refreshed.trip_instance_id)
    assert "Best current price so far is $180" in reason
    assert "still checking the remaining options" in reason


def test_rebook_uses_trip_level_best_option_when_booking_exists(repository: Repository) -> None:
    snapshot, instance, trackers = _single_instance_snapshot(
        repository,
        preference_mode="ranked_bias",
        payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            },
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "United",
                "day_offset": 0,
                "start_time": "18:00",
                "end_time": "22:00",
                "savings_needed_vs_previous": 50,
            },
        ],
    )

    booking = Booking(
        booking_id="book_1",
        trip_instance_id=instance.trip_instance_id,
        airline="Alaska",
        origin_airport="BUR",
        destination_airport="SFO",
        departure_date=instance.anchor_date,
        departure_time="07:00",
        booked_price=180,
        record_locator="BIAS01",
    )

    trackers[0].latest_observed_price = 180
    trackers[1].latest_observed_price = 130
    recompute_trip_states(snapshot.trip_instances, trackers, [booking])
    snapshot.bookings = [booking]
    refreshed = next(item for item in snapshot.trip_instances if item.trip_instance_id == instance.trip_instance_id)
    assert factual_trip_status_label(snapshot, refreshed.trip_instance_id) == "Lower fare found"
    reason = factual_trip_status_reason(snapshot, refreshed.trip_instance_id)
    assert "Current comparable price is $130" in reason
