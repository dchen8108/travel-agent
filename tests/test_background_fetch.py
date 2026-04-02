from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone

from app.models.base import utcnow
from app.models.booking import Booking
from app.models.price_record import PriceRecord
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip_instance import TripInstance
from app.jobs.fetch_google_flights import _non_negative_int
from app.services.background_fetch import queue_rolling_refresh, run_fetch_batch, select_due_fetch_targets
from app.services.dashboard import factual_trip_status_label, factual_trip_status_reason
from app.services.fetch_targets import (
    FETCH_INTERVAL_SECONDS,
    next_refresh_time,
    reconcile_fetch_targets,
    schedule_offset_for_trip,
)
from app.services.ids import new_id
from app.services.google_flights_fetcher import (
    GoogleFlightsNoResultsError,
    best_google_flights_offer,
    departure_time_from_offer_label,
    filter_google_flights_offers_by_departure_window,
    parse_google_flights_offers,
)
from app.services.price_records import build_price_records
from app.services.recommendations import apply_fetch_target_rollups, recompute_trip_states
from app.services.trips import save_trip
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


def test_route_options_reject_more_than_three_airports(repository: Repository) -> None:
    try:
        save_trip(
            repository,
            trip_id=None,
            label="Too many airports",
            trip_kind="one_time",
            active=True,
            anchor_date=date(2026, 4, 10),
            anchor_weekday="",
            route_option_payloads=[
                {
                    "origin_airports": "BUR|LAX|SNA|ONT",
                    "destination_airports": "SFO",
                    "airlines": "Alaska",
                    "day_offset": 0,
                    "start_time": "06:00",
                    "end_time": "10:00",
                }
            ],
        )
    except ValueError as exc:
        assert "at most three airports" in str(exc)
    else:
        raise AssertionError("Expected route option airport cap to be enforced.")


def test_fetch_job_rejects_negative_max_targets() -> None:
    try:
        _non_negative_int("-1")
    except Exception as exc:
        assert "--max-targets must be >= 0" in str(exc)
    else:
        raise AssertionError("Expected negative max-targets to be rejected.")


def test_next_refresh_time_uses_four_hour_cadence() -> None:
    now = datetime(2026, 3, 31, 7, 12, tzinfo=timezone.utc)
    assert FETCH_INTERVAL_SECONDS == 4 * 60 * 60
    assert next_refresh_time(now, 0) == datetime(2026, 3, 31, 8, 0, tzinfo=timezone.utc)
    assert next_refresh_time(now, 20) == datetime(2026, 3, 31, 8, 0, 20, tzinfo=timezone.utc)


def test_reconcile_fetch_targets_creates_every_airport_pair(repository: Repository) -> None:
    now = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)
    trip = save_trip(
        repository,
        trip_id=None,
        label="Fetch target matrix",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX|SNA",
                "destination_airports": "SFO|OAK",
                "airlines": "Alaska|United",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    tracker = next(item for item in snapshot.trackers if item.trip_instance_id in {instance.trip_instance_id for instance in snapshot.trip_instances if instance.trip_id == trip.trip_id})

    fetch_targets = reconcile_fetch_targets(
        snapshot.trackers,
        snapshot.trips,
        snapshot.trip_instances,
        [],
        now=now,
    )
    fetch_targets = [item for item in fetch_targets if item.tracker_id == tracker.tracker_id]
    assert len(fetch_targets) == 6
    assert {item.origin_airport for item in fetch_targets} == {"BUR", "LAX", "SNA"}
    assert {item.destination_airport for item in fetch_targets} == {"SFO", "OAK"}
    assert {item.schedule_offset_seconds for item in fetch_targets} == {schedule_offset_for_trip(trip.created_at)}
    ordered_refreshes = sorted(item.next_fetch_not_before for item in fetch_targets if item.next_fetch_not_before)
    assert ordered_refreshes[0] == now
    assert ordered_refreshes[-1] == now + timedelta(seconds=50)


def test_parse_google_flights_offers_extracts_prices_and_best_offer() -> None:
    html = """
    <html><body>
      <div jsname="IWWDBc">
        <ul class="Rk10dc">
          <li>
            <div class="sSHqwe tPgKwe ogfYpf"><span>Southwest</span></div>
            <span class="mv1WYe"><div>6:10 PM on Wed, Apr 1</div><div>7:20 PM on Wed, Apr 1</div></span>
            <div class="YMlIz FpEdX">$267</div>
          </li>
          <li>
            <div class="sSHqwe tPgKwe ogfYpf"><span>Alaska</span></div>
            <span class="mv1WYe"><div>5:55 PM on Wed, Apr 1</div><div>7:05 PM on Wed, Apr 1</div></span>
            <div class="YMlIz FpEdX">$241</div>
          </li>
        </ul>
      </div>
    </body></html>
    """

    offers = parse_google_flights_offers(html)
    winner = best_google_flights_offer(offers)

    assert len(offers) == 2
    assert winner is not None
    assert winner.airline == "Alaska"
    assert winner.price == 241


def test_departure_time_filter_supports_minute_precision() -> None:
    offers = parse_google_flights_offers(
        """
        <div jsname="IWWDBc">
          <ul class="Rk10dc">
            <li>
              <div class="sSHqwe tPgKwe ogfYpf"><span>Southwest</span></div>
              <span class="mv1WYe"><div>2:15 PM on Wed, Apr 1</div><div>3:30 PM on Wed, Apr 1</div></span>
              <div class="YMlIz FpEdX">$119</div>
            </li>
            <li>
              <div class="sSHqwe tPgKwe ogfYpf"><span>Alaska</span></div>
              <span class="mv1WYe"><div>2:45 PM on Wed, Apr 1</div><div>4:00 PM on Wed, Apr 1</div></span>
              <div class="YMlIz FpEdX">$129</div>
            </li>
            <li>
              <div class="sSHqwe tPgKwe ogfYpf"><span>United</span></div>
              <span class="mv1WYe"><div>5:45 PM on Wed, Apr 1</div><div>7:00 PM on Wed, Apr 1</div></span>
              <div class="YMlIz FpEdX">$109</div>
            </li>
          </ul>
        </div>
        """
    )

    assert departure_time_from_offer_label(offers[0].departure_label) == "14:15"
    matching = filter_google_flights_offers_by_departure_window(
        offers,
        start_time="14:30",
        end_time="17:30",
    )

    assert [offer.airline for offer in matching] == ["Alaska"]


def test_parse_google_flights_offers_distinguishes_no_results_from_parse_failures() -> None:
    no_results_html = "<html><body><p>No flights match your filters. Try changing your airports or dates.</p></body></html>"
    google_shell_no_results_html = """
    <html><body>
      <title>Burbank to San Francisco | Google Flights</title>
      <div>Flight search One way Round trip</div>
      <div>Select multiple airports</div>
      <div>All filters (3) Nonstop Airlines Times Bags Price Emissions Connecting airports Duration</div>
      <div>Connecting airports</div>
    </body></html>
    """
    broken_html = "<html><body><p>Unexpected shell with no matching offer nodes.</p></body></html>"

    try:
        parse_google_flights_offers(no_results_html)
    except GoogleFlightsNoResultsError:
        pass
    else:
        raise AssertionError("Expected no-results page to raise GoogleFlightsNoResultsError.")

    try:
        parse_google_flights_offers(google_shell_no_results_html)
    except GoogleFlightsNoResultsError:
        pass
    else:
        raise AssertionError("Expected Google search shell with no prices to raise GoogleFlightsNoResultsError.")

    try:
        parse_google_flights_offers(broken_html)
    except GoogleFlightsNoResultsError as exc:
        raise AssertionError("Unexpectedly classified parser breakage as no-results.") from exc
    except Exception:
        pass
    else:
        raise AssertionError("Expected broken parser input to raise an error.")


def test_select_due_fetch_targets_limits_to_one_target_per_tracker(repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Due target selection",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX",
                "destination_airports": "SFO|OAK",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            },
            {
                "origin_airports": "SFO",
                "destination_airports": "BUR",
                "airlines": "Alaska",
                "day_offset": 1,
                "start_time": "17:00",
                "end_time": "21:00",
            },
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    now = utcnow()
    for target in snapshot.tracker_fetch_targets:
        target.next_fetch_not_before = now - timedelta(seconds=1)

    due_targets = select_due_fetch_targets(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=3,
        now=now,
    )

    assert len(due_targets) == 2
    assert len({item.tracker_id for item in due_targets}) == 2


def test_select_due_fetch_targets_prioritizes_targets_without_a_price(repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Existing priced tracker",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=3),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )
    second_trip = save_trip(
        repository,
        trip_id=None,
        label="Needs first price",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SEA",
                "airlines": "Delta",
                "day_offset": 0,
                "start_time": "07:00",
                "end_time": "11:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository)
    now = utcnow()
    for target in snapshot.tracker_fetch_targets:
        target.next_fetch_not_before = now - timedelta(seconds=1)
        if target.origin_airport == "BUR":
            target.latest_price = 141
            target.latest_fetched_at = now - timedelta(hours=1)
            target.last_fetch_finished_at = now - timedelta(hours=1)
        else:
            target.latest_price = None
            target.latest_fetched_at = None
            target.last_fetch_finished_at = now - timedelta(minutes=5)

    due_targets = select_due_fetch_targets(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=1,
        now=now,
    )

    assert len(due_targets) == 1
    chosen_target = due_targets[0]
    chosen_instance = next(item for item in snapshot.trip_instances if item.trip_instance_id == chosen_target.trip_instance_id)
    assert chosen_instance.trip_id == second_trip.trip_id


def test_select_due_fetch_targets_returns_empty_when_max_targets_is_zero(repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Zero target selection",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=5),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository)
    now = utcnow()
    for target in snapshot.tracker_fetch_targets:
        target.next_fetch_not_before = now - timedelta(seconds=1)

    due_targets = select_due_fetch_targets(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=0,
        now=now,
    )

    assert due_targets == []


def test_select_due_fetch_targets_skips_past_trip_targets(repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Past fetch target selection",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 3, 20),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    now = utcnow()
    for target in snapshot.tracker_fetch_targets:
        target.next_fetch_not_before = now - timedelta(seconds=1)

    due_targets = select_due_fetch_targets(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=3,
        now=now,
    )

    assert due_targets == []


def test_queue_rolling_refresh_prioritizes_targets_without_a_price(repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Refresh queue priority A",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=3),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )
    save_trip(
        repository,
        trip_id=None,
        label="Refresh queue priority B",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SEA",
                "airlines": "Delta",
                "day_offset": 0,
                "start_time": "07:00",
                "end_time": "11:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository)
    now = utcnow()
    for target in snapshot.tracker_fetch_targets:
        target.next_fetch_not_before = now + timedelta(hours=3)
        if target.origin_airport == "BUR":
            target.latest_price = 141
            target.latest_fetched_at = now - timedelta(hours=1)
            target.last_fetch_finished_at = now - timedelta(hours=1)

    queue_rolling_refresh(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        now=now,
    )

    queued_targets = sorted(
        snapshot.tracker_fetch_targets,
        key=lambda item: item.next_fetch_not_before or now,
    )
    assert queued_targets[0].origin_airport == "LAX"
    assert queued_targets[0].destination_airport == "SEA"


def test_run_fetch_batch_updates_targets_and_rolls_up_prices(repository: Repository, monkeypatch) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Fetch batch success",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=7),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository)
    tracker = next(item for item in snapshot.trackers if item.trip_instance_id in {instance.trip_instance_id for instance in snapshot.trip_instances if instance.trip_id == trip.trip_id})
    for target in snapshot.tracker_fetch_targets:
        target.next_fetch_not_before = utcnow() - timedelta(seconds=1)

    seen_prices = iter([141, 188])

    def fake_fetch(url: str, *, client=None, timeout=20.0):
        price = next(seen_prices)
        return parse_google_flights_offers(
            f"""
            <div jsname=\"IWWDBc\">
              <ul class=\"Rk10dc\">
                <li>
                  <div class=\"sSHqwe tPgKwe ogfYpf\"><span>Alaska</span></div>
                  <span class=\"mv1WYe\"><div>6:15 AM on Tue, Apr 1</div><div>7:25 AM on Tue, Apr 1</div></span>
                  <div class=\"YMlIz FpEdX\">${price}</div>
                </li>
              </ul>
            </div>
            """
        )

    monkeypatch.setattr("app.services.background_fetch.fetch_google_flights_offers", fake_fetch)

    result = run_fetch_batch(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=2,
        sleep_between_requests=False,
    )
    apply_fetch_target_rollups(snapshot.trackers, snapshot.tracker_fetch_targets)

    assert result.fetched_count == 1
    assert result.selected_count == 1
    assert sum(target.latest_price is not None for target in snapshot.tracker_fetch_targets) == 1
    assert tracker.latest_observed_price == 141
    assert tracker.latest_signal_source == "background_fetch"
    assert tracker.latest_winning_origin_airport == "BUR"
    assert tracker.latest_winning_destination_airport == "SFO"
    assert len(result.successful_fetches) == 1
    assert len(result.attempts) == 1
    assert result.attempts[0].status == "success"
    assert result.attempts[0].price == 141
    assert result.attempts[0].offer_count == 1
    assert result.attempts[0].matching_offer_count == 1


def test_run_fetch_batch_with_zero_max_targets_is_a_no_op(repository: Repository, monkeypatch) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Zero batch selection",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=7),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository)
    for target in snapshot.tracker_fetch_targets:
        target.next_fetch_not_before = utcnow() - timedelta(seconds=1)

    def should_not_fetch(url: str, *, client=None, timeout=20.0):
        raise AssertionError("Fetcher should not run when max_targets=0")

    monkeypatch.setattr("app.services.background_fetch.fetch_google_flights_offers", should_not_fetch)

    result = run_fetch_batch(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=0,
        sleep_between_requests=False,
    )

    assert result.fetched_count == 0
    assert result.selected_count == 0
    assert result.attempts == []
    assert result.successful_fetches == []


def test_run_fetch_batch_applies_startup_jitter_when_requested(repository: Repository, monkeypatch) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Startup jitter test",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=7),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository)
    for target in snapshot.tracker_fetch_targets:
        target.next_fetch_not_before = utcnow() - timedelta(seconds=1)

    sleep_calls: list[float] = []

    def fake_sleep(value: float) -> None:
        sleep_calls.append(value)

    def fake_uniform(start: float, end: float) -> float:
        assert start == 0.0
        assert end == 8.0
        return 4.25

    def fake_fetch(url: str, *, client=None, timeout=20.0):
        return parse_google_flights_offers(
            """
            <div jsname="IWWDBc">
              <ul class="Rk10dc">
                <li>
                  <div class="sSHqwe tPgKwe ogfYpf"><span>Alaska</span></div>
                  <span class="mv1WYe"><div>6:15 AM on Tue, Apr 1</div><div>7:25 AM on Tue, Apr 1</div></span>
                  <div class="YMlIz FpEdX">$141</div>
                </li>
              </ul>
            </div>
            """
        )

    monkeypatch.setattr("app.services.background_fetch.time.sleep", fake_sleep)
    monkeypatch.setattr("app.services.background_fetch.random.uniform", fake_uniform)
    monkeypatch.setattr("app.services.background_fetch.fetch_google_flights_offers", fake_fetch)

    result = run_fetch_batch(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=1,
        sleep_between_requests=False,
        startup_jitter_seconds=8.0,
    )

    assert result.fetched_count == 1
    assert result.startup_jitter_applied_seconds == 4.25
    assert sleep_calls == [4.25]


def test_run_fetch_batch_marks_no_results_without_counting_a_failure(repository: Repository, monkeypatch) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="No results test",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=7),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository)
    target = snapshot.tracker_fetch_targets[0]
    target.latest_price = 141
    target.latest_airline = "Alaska"
    target.latest_summary = "Old price"
    target.latest_fetched_at = utcnow() - timedelta(hours=1)
    target.next_fetch_not_before = utcnow() - timedelta(seconds=1)

    def fake_fetch(url: str, *, client=None, timeout=20.0):
        raise GoogleFlightsNoResultsError("No flight prices found in the Google Flights response.")

    monkeypatch.setattr("app.services.background_fetch.fetch_google_flights_offers", fake_fetch)

    result = run_fetch_batch(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=1,
        sleep_between_requests=False,
        startup_jitter_seconds=0,
    )

    assert result.fetched_count == 1
    assert len(result.attempts) == 1
    assert result.attempts[0].status == "no_results"
    assert result.attempts[0].matching_offer_count == 0
    assert target.last_fetch_status == "no_results"
    assert target.consecutive_failures == 0
    assert target.last_fetch_error == "No flight prices found in the Google Flights response."
    assert target.latest_price is None
    assert target.latest_airline == ""
    assert target.latest_summary == ""


def test_run_fetch_batch_filters_winner_by_exact_departure_window_but_still_records_all_offers(
    repository: Repository,
    monkeypatch,
) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Precise departure window",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=7),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska|Southwest|United",
                "day_offset": 0,
                "start_time": "14:30",
                "end_time": "17:30",
            }
        ],
    )

    snapshot = sync_and_persist(repository)
    tracker = next(item for item in snapshot.trackers if item.trip_instance_id in {instance.trip_instance_id for instance in snapshot.trip_instances if instance.trip_id == trip.trip_id})
    for target in snapshot.tracker_fetch_targets:
        target.next_fetch_not_before = utcnow() - timedelta(seconds=1)

    def fake_fetch(url: str, *, client=None, timeout=20.0):
        return parse_google_flights_offers(
            """
            <div jsname="IWWDBc">
              <ul class="Rk10dc">
                <li>
                  <div class="sSHqwe tPgKwe ogfYpf"><span>Southwest</span></div>
                  <span class="mv1WYe"><div>2:15 PM on Wed, Apr 1</div><div>3:30 PM on Wed, Apr 1</div></span>
                  <div class="YMlIz FpEdX">$119</div>
                </li>
                <li>
                  <div class="sSHqwe tPgKwe ogfYpf"><span>Alaska</span></div>
                  <span class="mv1WYe"><div>2:45 PM on Wed, Apr 1</div><div>4:00 PM on Wed, Apr 1</div></span>
                  <div class="YMlIz FpEdX">$129</div>
                </li>
                <li>
                  <div class="sSHqwe tPgKwe ogfYpf"><span>United</span></div>
                  <span class="mv1WYe"><div>5:45 PM on Wed, Apr 1</div><div>7:00 PM on Wed, Apr 1</div></span>
                  <div class="YMlIz FpEdX">$109</div>
                </li>
              </ul>
            </div>
            """
        )

    monkeypatch.setattr("app.services.background_fetch.fetch_google_flights_offers", fake_fetch)

    result = run_fetch_batch(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=1,
        sleep_between_requests=False,
        startup_jitter_seconds=0,
    )

    assert result.attempts[0].status == "success"
    assert result.attempts[0].price == 129
    assert result.attempts[0].offer_count == 3
    assert result.attempts[0].matching_offer_count == 1

    apply_fetch_target_rollups(snapshot.trackers, snapshot.tracker_fetch_targets)
    assert tracker.latest_observed_price == 129

    records = build_price_records(
        trips=snapshot.trips,
        trip_instances=snapshot.trip_instances,
        trackers=snapshot.trackers,
        fetch_targets=snapshot.tracker_fetch_targets,
        successful_fetches=result.successful_fetches,
    )
    assert len(records) == 3
    assert {record.price for record in records} == {109, 119, 129}


def test_run_fetch_batch_marks_no_results_when_broad_query_returns_only_out_of_window_offers(
    repository: Repository,
    monkeypatch,
) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Out of window only",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=7),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska|Southwest|United",
                "day_offset": 0,
                "start_time": "14:30",
                "end_time": "17:30",
            }
        ],
    )

    snapshot = sync_and_persist(repository)
    for target in snapshot.tracker_fetch_targets:
        target.next_fetch_not_before = utcnow() - timedelta(seconds=1)

    def fake_fetch(url: str, *, client=None, timeout=20.0):
        return parse_google_flights_offers(
            """
            <div jsname="IWWDBc">
              <ul class="Rk10dc">
                <li>
                  <div class="sSHqwe tPgKwe ogfYpf"><span>Southwest</span></div>
                  <span class="mv1WYe"><div>2:15 PM on Wed, Apr 1</div><div>3:30 PM on Wed, Apr 1</div></span>
                  <div class="YMlIz FpEdX">$119</div>
                </li>
                <li>
                  <div class="sSHqwe tPgKwe ogfYpf"><span>United</span></div>
                  <span class="mv1WYe"><div>5:45 PM on Wed, Apr 1</div><div>7:00 PM on Wed, Apr 1</div></span>
                  <div class="YMlIz FpEdX">$109</div>
                </li>
              </ul>
            </div>
            """
        )

    monkeypatch.setattr("app.services.background_fetch.fetch_google_flights_offers", fake_fetch)

    result = run_fetch_batch(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=1,
        sleep_between_requests=False,
        startup_jitter_seconds=0,
    )

    assert result.attempts[0].status == "no_window_match"
    assert result.attempts[0].offer_count == 2
    assert result.attempts[0].matching_offer_count == 0
    assert "exact departure window" in result.attempts[0].error

    records = build_price_records(
        trips=snapshot.trips,
        trip_instances=snapshot.trip_instances,
        trackers=snapshot.trackers,
        fetch_targets=snapshot.tracker_fetch_targets,
        successful_fetches=result.successful_fetches,
    )
    assert len(records) == 2


def test_fetch_rollup_clears_background_only_tracker_when_targets_reset() -> None:
    tracker = Tracker(
        tracker_id="trk_1",
        trip_instance_id="inst_1",
        route_option_id="opt_1",
        rank=1,
        origin_airports="BUR|LAX",
        destination_airports="SFO",
        airlines="Alaska",
        day_offset=0,
        travel_date=date(2026, 4, 10),
        start_time="06:00",
        end_time="10:00",
        latest_observed_price=141,
        latest_fetched_at=utcnow(),
        last_signal_at=utcnow(),
        latest_winning_origin_airport="BUR",
        latest_winning_destination_airport="SFO",
        latest_signal_source="background_fetch",
        latest_match_summary="Fetched via BUR → SFO",
    )

    apply_fetch_target_rollups([tracker], [])

    assert tracker.latest_observed_price is None
    assert tracker.latest_signal_source == ""
    assert tracker.latest_winning_origin_airport == ""
    assert tracker.latest_winning_destination_airport == ""


def test_fetch_rollup_uses_recent_price_window_instead_of_stale_cheapest_price() -> None:
    tracker = Tracker(
        tracker_id="trk_1",
        trip_instance_id="inst_1",
        route_option_id="opt_1",
        rank=1,
        origin_airports="BUR|LAX",
        destination_airports="SFO",
        airlines="Alaska",
        day_offset=0,
        travel_date=date(2026, 4, 10),
        start_time="06:00",
        end_time="10:00",
    )
    now = utcnow()
    stale_cheap = TrackerFetchTarget(
        fetch_target_id="ft_stale",
        tracker_id="trk_1",
        trip_instance_id="inst_1",
        origin_airport="BUR",
        destination_airport="SFO",
        google_flights_url="https://www.google.com/travel/flights/search?tfs=stale",
        latest_price=120,
        latest_airline="Alaska",
        latest_summary="Stale cheap",
        latest_fetched_at=now - timedelta(days=7),
    )
    fresh_higher = TrackerFetchTarget(
        fetch_target_id="ft_fresh",
        tracker_id="trk_1",
        trip_instance_id="inst_1",
        origin_airport="LAX",
        destination_airport="SFO",
        google_flights_url="https://www.google.com/travel/flights/search?tfs=fresh",
        latest_price=149,
        latest_airline="Alaska",
        latest_summary="Fresh higher",
        latest_fetched_at=now,
    )

    apply_fetch_target_rollups([tracker], [stale_cheap, fresh_higher])

    assert tracker.latest_observed_price == 149
    assert tracker.latest_winning_origin_airport == "LAX"


def test_fetch_rollup_clears_tracker_when_only_stale_fetch_prices_remain() -> None:
    tracker = Tracker(
        tracker_id="trk_1",
        trip_instance_id="inst_1",
        route_option_id="opt_1",
        rank=1,
        origin_airports="BUR",
        destination_airports="SFO",
        airlines="Alaska",
        day_offset=0,
        travel_date=date(2026, 4, 10),
        start_time="06:00",
        end_time="10:00",
        latest_observed_price=141,
        latest_fetched_at=utcnow() - timedelta(days=8),
        last_signal_at=utcnow() - timedelta(days=8),
        latest_winning_origin_airport="BUR",
        latest_winning_destination_airport="SFO",
        latest_signal_source="background_fetch",
        latest_match_summary="Old fetched price",
    )
    stale_target = TrackerFetchTarget(
        fetch_target_id="ft_stale",
        tracker_id="trk_1",
        trip_instance_id="inst_1",
        origin_airport="BUR",
        destination_airport="SFO",
        google_flights_url="https://www.google.com/travel/flights/search?tfs=stale",
        latest_price=141,
        latest_airline="Alaska",
        latest_summary="Old fetched price",
        latest_fetched_at=utcnow() - timedelta(days=8),
    )

    apply_fetch_target_rollups([tracker], [stale_target])

    assert tracker.latest_observed_price is None
    assert tracker.latest_signal_source == ""


def test_reconcile_fetch_targets_rebalances_legacy_offsets(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Offset rebalance",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )
    initial = sync_and_persist(repository, today=date(2026, 4, 1))
    tracker = next(
        item
        for item in initial.trackers
        if item.trip_instance_id in {
            instance.trip_instance_id for instance in initial.trip_instances if instance.trip_id == trip.trip_id
        }
    )
    legacy_targets = [
        TrackerFetchTarget(
            fetch_target_id=item.fetch_target_id,
            tracker_id=item.tracker_id,
            trip_instance_id=item.trip_instance_id,
            tracker_definition_signature=tracker.definition_signature,
            origin_airport=item.origin_airport,
            destination_airport=item.destination_airport,
            schedule_offset_seconds=0,
            google_flights_url=item.google_flights_url,
            next_fetch_not_before=utcnow(),
        )
        for item in initial.tracker_fetch_targets
        if item.tracker_id == tracker.tracker_id
    ]

    rebalanced = reconcile_fetch_targets([tracker], initial.trips, initial.trip_instances, legacy_targets)

    assert {item.schedule_offset_seconds for item in rebalanced} == {schedule_offset_for_trip(trip.created_at)}
    assert len({item.next_fetch_not_before for item in rebalanced}) == 1


def test_reconcile_fetch_targets_immediately_requeues_definition_changes(repository: Repository) -> None:
    now = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    trip = save_trip(
        repository,
        trip_id=None,
        label="Immediate refresh on edit",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )
    initial = sync_and_persist(repository, today=date(2026, 4, 1))
    tracker = next(
        item
        for item in initial.trackers
        if item.trip_instance_id in {
            instance.trip_instance_id for instance in initial.trip_instances if instance.trip_id == trip.trip_id
        }
    )
    original_target = next(item for item in initial.tracker_fetch_targets if item.tracker_id == tracker.tracker_id)
    original_target.latest_price = 141
    original_target.latest_airline = "Alaska"
    original_target.latest_summary = "Old price"
    original_target.latest_fetched_at = now - timedelta(hours=1)
    original_target.last_fetch_finished_at = now - timedelta(hours=1)
    original_target.next_fetch_not_before = now + timedelta(hours=3)

    tracker.start_time = "06:15"
    tracker.end_time = "10:15"
    tracker.definition_signature = "changed-definition"

    refreshed = reconcile_fetch_targets(
        [tracker],
        initial.trips,
        initial.trip_instances,
        [original_target],
        now=now,
    )

    updated_target = refreshed[0]
    assert updated_target.next_fetch_not_before == now
    assert updated_target.latest_price is None
    assert updated_target.last_fetch_status == "pending"
    assert updated_target.tracker_definition_signature == "changed-definition"
def test_booked_trip_uses_trip_level_best_tracker_for_rebook_checks() -> None:
    trip_instance = TripInstance(
        trip_instance_id="inst_1",
        trip_id="trip_1",
        display_label="Commute",
        anchor_date=date.today() + timedelta(days=7),
        booking_id="book_1",
    )
    booked_tracker = Tracker(
        tracker_id="trk_booked",
        trip_instance_id="inst_1",
        route_option_id="opt_1",
        rank=1,
        origin_airports="BUR",
        destination_airports="SFO",
        airlines="Alaska",
        day_offset=0,
        travel_date=trip_instance.anchor_date,
        start_time="06:00",
        end_time="10:00",
        latest_observed_price=180,
        last_signal_at=utcnow(),
        latest_signal_source="background_fetch",
    )
    cheaper_other_tracker = Tracker(
        tracker_id="trk_other",
        trip_instance_id="inst_1",
        route_option_id="opt_2",
        rank=2,
        origin_airports="LAX",
        destination_airports="SFO",
        airlines="Alaska",
        day_offset=0,
        travel_date=trip_instance.anchor_date,
        start_time="06:00",
        end_time="10:00",
        latest_observed_price=120,
        last_signal_at=utcnow(),
        latest_signal_source="background_fetch",
    )
    booking = Booking(
        booking_id="book_1",
        trip_instance_id="inst_1",
        airline="Alaska",
        origin_airport="BUR",
        destination_airport="SFO",
        departure_date=trip_instance.anchor_date,
        departure_time="07:00",
        booked_price=150,
        record_locator="ABC123",
    )

    recompute_trip_states([trip_instance], [booked_tracker, cheaper_other_tracker], [booking])

    snapshot = type(
        "Snapshot",
        (),
        {
            "trip_instances": [trip_instance],
            "trackers": [booked_tracker, cheaper_other_tracker],
            "bookings": [booking],
        },
    )()
    assert factual_trip_status_label(snapshot, trip_instance.trip_instance_id) == "Lower fare found"
    assert "Current comparable price is $120" in factual_trip_status_reason(snapshot, trip_instance.trip_instance_id)


def test_queue_rolling_refresh_pulls_due_times_forward_in_staggered_order(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Manual refresh wave",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )
    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    tracker = next(
        item
        for item in snapshot.trackers
        if item.trip_instance_id in {
            instance.trip_instance_id for instance in snapshot.trip_instances if instance.trip_id == trip.trip_id
        }
    )
    now = utcnow()

    queued_count = queue_rolling_refresh(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        now=now,
    )

    targets = [item for item in snapshot.tracker_fetch_targets if item.tracker_id == tracker.tracker_id]
    targets.sort(key=lambda item: item.next_fetch_not_before or now)
    assert queued_count == 2
    assert targets[0].next_fetch_not_before == now
    assert targets[1].next_fetch_not_before == now + timedelta(seconds=10)


def test_recompute_trip_states_uses_explicit_today_without_calling_date_today(monkeypatch) -> None:
    class DateProxy:
        @staticmethod
        def today():
            raise AssertionError("recompute_trip_states should use the explicit today parameter")

    monkeypatch.setattr("app.services.recommendations.date", DateProxy)

    trip_instance = TripInstance(
        trip_instance_id="inst_1",
        trip_id="trip_1",
        display_label="Trip",
        anchor_date=date(2026, 4, 1),
    )

    recompute_trip_states([trip_instance], [], [], today=date(2026, 3, 31))

    assert trip_instance.travel_state == "open"


def test_run_fetch_batch_reraises_unexpected_exceptions(repository: Repository, monkeypatch) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Unexpected fetch bug",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=7),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )
    snapshot = sync_and_persist(repository)
    for target in snapshot.tracker_fetch_targets:
        target.next_fetch_not_before = utcnow() - timedelta(seconds=1)

    monkeypatch.setattr(
        "app.services.background_fetch.fetch_google_flights_offers",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("unexpected parser bug")),
    )

    try:
        run_fetch_batch(
            snapshot.trackers,
            snapshot.trip_instances,
            snapshot.tracker_fetch_targets,
            max_targets=1,
            sleep_between_requests=False,
        )
    except ValueError as exc:
        assert "unexpected parser bug" in str(exc)
    else:
        raise AssertionError("Expected unexpected fetch exceptions to bubble out of run_fetch_batch.")


def test_successful_fetch_builds_price_records_for_all_offers(repository: Repository, monkeypatch) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Price history build",
        trip_kind="one_time",
        active=True,
        anchor_date=date.today() + timedelta(days=7),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR",
                "destination_airports": "SFO",
                "airlines": "Alaska|Southwest",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository)
    for target in snapshot.tracker_fetch_targets:
        target.next_fetch_not_before = utcnow() - timedelta(seconds=1)

    def fake_fetch(url: str, *, client=None, timeout=20.0):
        return parse_google_flights_offers(
            """
            <div jsname=\"IWWDBc\">
              <ul class=\"Rk10dc\">
                <li>
                  <div class=\"sSHqwe tPgKwe ogfYpf\"><span>Southwest</span></div>
                  <span class=\"mv1WYe\"><div>6:10 PM on Wed, Apr 1</div><div>7:20 PM on Wed, Apr 1</div></span>
                  <div class=\"YMlIz FpEdX\">$267</div>
                </li>
                <li>
                  <div class=\"sSHqwe tPgKwe ogfYpf\"><span>Alaska</span></div>
                  <span class=\"mv1WYe\"><div>5:55 PM on Wed, Apr 1</div><div>7:05 PM on Wed, Apr 1</div></span>
                  <div class=\"YMlIz FpEdX\">$241</div>
                </li>
              </ul>
            </div>
            """
        )

    monkeypatch.setattr("app.services.background_fetch.fetch_google_flights_offers", fake_fetch)

    result = run_fetch_batch(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=1,
        sleep_between_requests=False,
    )
    records = build_price_records(
        trips=snapshot.trips,
        trip_instances=snapshot.trip_instances,
        trackers=snapshot.trackers,
        fetch_targets=snapshot.tracker_fetch_targets,
        successful_fetches=result.successful_fetches,
    )
    repository.append_price_records(records)

    saved_records = repository.load_price_records()
    assert len(saved_records) == 2
    assert {item.price for item in saved_records} == {241, 267}
    assert all(item.fetch_target_id == snapshot.tracker_fetch_targets[0].fetch_target_id for item in saved_records)
    assert all(item.search_origin_airports == "BUR" for item in saved_records)
    assert all(item.query_origin_airport == "BUR" for item in saved_records)
    assert all(item.query_destination_airport == "SFO" for item in saved_records)
    assert saved_records[0].fetch_event_id == saved_records[1].fetch_event_id
    assert saved_records[0].offer_rank == 1
    assert saved_records[1].offer_rank == 2
    assert all(item.search_fare_class_policy == "include_basic" for item in saved_records)


def test_append_price_records_migrates_legacy_header(settings) -> None:
    repository = Repository(settings)
    path = repository.settings.data_dir / "price_records.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy_fieldnames = [
        "price_record_id",
        "fetch_event_id",
        "observed_at",
        "observed_date",
        "source",
        "provider",
        "fetch_method",
        "fetch_target_id",
        "tracker_id",
        "trip_instance_id",
        "trip_id",
        "route_option_id",
        "tracker_definition_signature",
        "trip_label",
        "tracker_rank",
        "search_origin_airports",
        "search_destination_airports",
        "search_airlines",
        "search_day_offset",
        "search_travel_date",
        "search_start_time",
        "search_end_time",
        "query_origin_airport",
        "query_destination_airport",
        "google_flights_url",
        "airline",
        "departure_label",
        "arrival_label",
        "price",
        "offer_rank",
        "price_text",
        "summary",
        "request_offer_count",
        "is_request_cheapest",
        "record_signature",
        "created_at",
    ]
    observed_at = utcnow()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=legacy_fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "price_record_id": "price_old",
                "fetch_event_id": "fetch_old",
                "observed_at": observed_at.isoformat(),
                "observed_date": observed_at.date().isoformat(),
                "source": "background_fetch",
                "provider": "google_flights",
                "fetch_method": "generated_link",
                "fetch_target_id": "ft_old",
                "tracker_id": "trk_old",
                "trip_instance_id": "inst_old",
                "trip_id": "trip_old",
                "route_option_id": "opt_old",
                "tracker_definition_signature": "sig_old",
                "trip_label": "Legacy trip",
                "tracker_rank": 1,
                "search_origin_airports": "BUR",
                "search_destination_airports": "SFO",
                "search_airlines": "Alaska",
                "search_day_offset": 0,
                "search_travel_date": date(2026, 4, 1).isoformat(),
                "search_start_time": "06:00",
                "search_end_time": "10:00",
                "query_origin_airport": "BUR",
                "query_destination_airport": "SFO",
                "google_flights_url": "https://www.google.com/travel/flights/search?tfs=legacy",
                "airline": "Alaska",
                "departure_label": "6:00 AM",
                "arrival_label": "7:30 AM",
                "price": 199,
                "offer_rank": 1,
                "price_text": "$199",
                "summary": "Legacy summary",
                "request_offer_count": 1,
                "is_request_cheapest": True,
                "record_signature": "legacy_sig",
                "created_at": observed_at.isoformat(),
            }
        )

    repository.ensure_data_dir()
    repository.append_price_records(
        [
            PriceRecord(
                price_record_id="price_new",
                fetch_event_id="fetch_new",
                observed_at=observed_at,
                fetch_target_id="ft_new",
                tracker_id="trk_new",
                trip_instance_id="inst_new",
                trip_id="trip_new",
                route_option_id="opt_new",
                tracker_definition_signature="sig_new",
                tracker_rank=1,
                search_origin_airports="LAX",
                search_destination_airports="SFO",
                search_airlines="United",
                search_day_offset=0,
                search_travel_date=date(2026, 4, 2),
                search_start_time="07:00",
                search_end_time="11:00",
                query_origin_airport="LAX",
                query_destination_airport="SFO",
                airline="United",
                departure_label="7:05 AM",
                arrival_label="8:35 AM",
                price=209,
                offer_rank=1,
            )
        ]
    )

    saved_records = repository.load_price_records()
    assert len(saved_records) == 2
    assert {item.price_record_id for item in saved_records} == {"price_old", "price_new"}
    legacy = next(item for item in saved_records if item.price_record_id == "price_old")
    assert legacy.price == 199
    assert legacy.offer_rank == 1
    assert legacy.query_origin_airport == "BUR"


def test_load_price_records_ignores_removed_legacy_columns(settings) -> None:
    repository = Repository(settings)
    path = repository.settings.data_dir / "price_records.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy_fieldnames = [
        "price_record_id",
        "fetch_event_id",
        "observed_at",
        "observed_date",
        "source",
        "provider",
        "fetch_method",
        "fetch_target_id",
        "tracker_id",
        "trip_instance_id",
        "trip_id",
        "route_option_id",
        "tracker_definition_signature",
        "trip_label",
        "tracker_rank",
        "search_origin_airports",
        "search_destination_airports",
        "search_airlines",
        "search_day_offset",
        "search_travel_date",
        "search_start_time",
        "search_end_time",
        "query_origin_airport",
        "query_destination_airport",
        "google_flights_url",
        "airline",
        "departure_label",
        "arrival_label",
        "price",
        "offer_rank",
        "price_text",
        "summary",
        "request_offer_count",
        "is_request_cheapest",
        "record_signature",
        "created_at",
    ]
    observed_at = utcnow()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=legacy_fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "price_record_id": "price_old",
                "fetch_event_id": "fetch_old",
                "observed_at": observed_at.isoformat(),
                "observed_date": observed_at.date().isoformat(),
                "source": "background_fetch",
                "provider": "google_flights",
                "fetch_method": "generated_link",
                "fetch_target_id": "ft_old",
                "tracker_id": "trk_old",
                "trip_instance_id": "inst_old",
                "trip_id": "trip_old",
                "route_option_id": "opt_old",
                "tracker_definition_signature": "sig_old",
                "trip_label": "Legacy trip",
                "tracker_rank": 1,
                "search_origin_airports": "BUR",
                "search_destination_airports": "SFO",
                "search_airlines": "Alaska",
                "search_day_offset": 0,
                "search_travel_date": date(2026, 4, 1).isoformat(),
                "search_start_time": "06:00",
                "search_end_time": "10:00",
                "query_origin_airport": "BUR",
                "query_destination_airport": "SFO",
                "google_flights_url": "https://www.google.com/travel/flights/search?tfs=legacy",
                "airline": "Alaska",
                "departure_label": "6:00 AM",
                "arrival_label": "7:30 AM",
                "price": 199,
                "offer_rank": 1,
                "price_text": "$199",
                "summary": "Legacy summary",
                "request_offer_count": 1,
                "is_request_cheapest": True,
                "record_signature": "legacy_sig",
                "created_at": observed_at.isoformat(),
            }
        )

    repository.ensure_data_dir()
    saved_records = repository.load_price_records()
    assert len(saved_records) == 1
    assert saved_records[0].price_record_id == "price_old"
    assert saved_records[0].price == 199
    assert saved_records[0].offer_rank == 1
