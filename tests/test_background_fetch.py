from __future__ import annotations

from datetime import date, timedelta

from app.models.base import TrackerStatus, utcnow
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.services.background_fetch import run_fetch_batch, select_due_fetch_targets
from app.services.fetch_targets import reconcile_fetch_targets
from app.services.google_flights_fetcher import best_google_flights_offer, parse_google_flights_offers
from app.services.recommendations import apply_fetch_target_rollups
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


def test_reconcile_fetch_targets_creates_every_airport_pair(repository: Repository) -> None:
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

    fetch_targets = [item for item in snapshot.tracker_fetch_targets if item.tracker_id == tracker.tracker_id]
    assert len(fetch_targets) == 6
    assert {item.origin_airport for item in fetch_targets} == {"BUR", "LAX", "SNA"}
    assert {item.destination_airport for item in fetch_targets} == {"SFO", "OAK"}


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
    for tracker in snapshot.trackers:
        tracker.tracking_status = TrackerStatus.TRACKING_ENABLED

    due_targets = select_due_fetch_targets(
        snapshot.trackers,
        snapshot.trip_instances,
        snapshot.tracker_fetch_targets,
        max_targets=3,
        now=utcnow(),
    )

    assert len(due_targets) == 2
    assert len({item.tracker_id for item in due_targets}) == 2


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
    tracker.tracking_status = TrackerStatus.TRACKING_ENABLED

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
    assert sum(target.latest_price is not None for target in snapshot.tracker_fetch_targets) == 1
    assert tracker.latest_observed_price == 141
    assert tracker.latest_signal_source == "background_fetch"
    assert tracker.latest_winning_origin_airport == "BUR"
    assert tracker.latest_winning_destination_airport == "SFO"


def test_fetch_rollup_does_not_override_newer_manual_signal() -> None:
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
        tracking_status=TrackerStatus.SIGNAL_RECEIVED,
        latest_observed_price=189,
        last_signal_at=utcnow(),
        latest_signal_source="manual_import",
    )
    older_target = TrackerFetchTarget(
        fetch_target_id="ft_1",
        tracker_id="trk_1",
        trip_instance_id="inst_1",
        origin_airport="BUR",
        destination_airport="SFO",
        google_flights_url="https://www.google.com/travel/flights/search?tfs=test",
        latest_price=141,
        latest_airline="Alaska",
        latest_summary="Alaska · $141",
        latest_fetched_at=tracker.last_signal_at - timedelta(hours=1),
    )

    apply_fetch_target_rollups([tracker], [older_target])

    assert tracker.latest_observed_price == 189
    assert tracker.latest_signal_source == "manual_import"
    assert tracker.latest_winning_origin_airport == ""
    assert tracker.latest_winning_destination_airport == ""


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
        tracking_status=TrackerStatus.SIGNAL_RECEIVED,
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
    assert tracker.tracking_status == TrackerStatus.NEEDS_SETUP


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
        tracking_status=TrackerStatus.TRACKING_ENABLED,
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
        tracking_status=TrackerStatus.SIGNAL_RECEIVED,
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
