from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone

from app.models.base import RecommendationState, TrackerStatus, utcnow
from app.models.booking import Booking
from app.models.price_record import PriceRecord
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip_instance import TripInstance
from app.services.background_fetch import queue_rolling_refresh, run_fetch_batch, select_due_fetch_targets
from app.services.fetch_targets import FETCH_INTERVAL_SECONDS, next_refresh_time, reconcile_fetch_targets
from app.services.ids import new_id
from app.services.google_flights_fetcher import best_google_flights_offer, parse_google_flights_offers
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


def test_next_refresh_time_uses_six_hour_cadence() -> None:
    now = datetime(2026, 3, 31, 7, 12, tzinfo=timezone.utc)
    assert FETCH_INTERVAL_SECONDS == 6 * 60 * 60
    assert next_refresh_time(now, 0) == datetime(2026, 3, 31, 12, 0, tzinfo=timezone.utc)
    assert next_refresh_time(now, 20) == datetime(2026, 3, 31, 12, 0, 20, tzinfo=timezone.utc)


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
    assert [item.schedule_offset_seconds for item in fetch_targets] == [0, 10, 20, 30, 40, 50]


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
    assert sum(target.latest_price is not None for target in snapshot.tracker_fetch_targets) == 1
    assert tracker.latest_observed_price == 141
    assert tracker.latest_signal_source == "background_fetch"
    assert tracker.latest_winning_origin_airport == "BUR"
    assert tracker.latest_winning_destination_airport == "SFO"
    assert len(result.successful_fetches) == 1
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
    assert tracker.tracking_status == TrackerStatus.TRACKING_ENABLED


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
            origin_airport=item.origin_airport,
            destination_airport=item.destination_airport,
            schedule_offset_seconds=0,
            google_flights_url=item.google_flights_url,
            next_fetch_not_before=utcnow(),
        )
        for item in initial.tracker_fetch_targets
        if item.tracker_id == tracker.tracker_id
    ]

    rebalanced = reconcile_fetch_targets([tracker], legacy_targets)

    assert [item.schedule_offset_seconds for item in rebalanced] == [0, 10]
    assert rebalanced[0].next_fetch_not_before != rebalanced[1].next_fetch_not_before
def test_booked_trip_prefers_its_attached_tracker_for_rebook_checks() -> None:
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
        tracker_id="trk_booked",
        airline="Alaska",
        origin_airport="BUR",
        destination_airport="SFO",
        departure_date=trip_instance.anchor_date,
        departure_time="07:00",
        booked_price=150,
        record_locator="ABC123",
    )

    recompute_trip_states([trip_instance], [booked_tracker, cheaper_other_tracker], [booking])

    assert trip_instance.recommendation_state == RecommendationState.BOOKED_MONITORING
    assert "Monitoring" in trip_instance.recommendation_reason


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
    assert all(item.trip_label == trip.label for item in saved_records)
    assert all(item.search_origin_airports == "BUR" for item in saved_records)
    assert all(item.query_origin_airport == "BUR" for item in saved_records)
    assert all(item.query_destination_airport == "SFO" for item in saved_records)
    assert saved_records[0].fetch_event_id == saved_records[1].fetch_event_id
    assert all(item.provider == "google_flights" for item in saved_records)
    assert all(item.fetch_method == "generated_link" for item in saved_records)
    assert all(item.observed_date == item.observed_at.date() for item in saved_records)
    assert saved_records[0].request_offer_count == 2
    assert saved_records[1].request_offer_count == 2
    assert saved_records[0].offer_rank == 1
    assert saved_records[1].offer_rank == 2
    assert saved_records[0].is_request_cheapest is True
    assert saved_records[1].is_request_cheapest is False
    assert saved_records[0].record_signature != saved_records[1].record_signature


def test_append_price_records_migrates_legacy_header(repository: Repository) -> None:
    path = repository.settings.data_dir / "price_records.csv"
    legacy_fieldnames = [
        "price_record_id",
        "fetch_event_id",
        "observed_at",
        "source",
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
        "price_text",
        "summary",
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
                "source": "background_fetch",
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
                "price_text": "$199",
                "summary": "Legacy summary",
                "created_at": observed_at.isoformat(),
            }
        )

    repository.append_price_records(
        [
            PriceRecord(
                price_record_id="price_new",
                fetch_event_id="fetch_new",
                observed_at=observed_at,
                source="background_fetch",
                fetch_target_id="ft_new",
                tracker_id="trk_new",
                trip_instance_id="inst_new",
                trip_id="trip_new",
                route_option_id="opt_new",
                tracker_definition_signature="sig_new",
                trip_label="New trip",
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
                google_flights_url="https://www.google.com/travel/flights/search?tfs=new",
                airline="United",
                departure_label="7:05 AM",
                arrival_label="8:35 AM",
                price=209,
                price_text="$209",
                summary="New summary",
                record_signature="sig_record_new",
            )
        ]
    )

    saved_records = repository.load_price_records()
    assert len(saved_records) == 2
    assert {item.price_record_id for item in saved_records} == {"price_old", "price_new"}
    legacy = next(item for item in saved_records if item.price_record_id == "price_old")
    assert legacy.observed_date == observed_at.date()


def test_load_price_records_backfills_observed_date_from_legacy_rows(repository: Repository) -> None:
    path = repository.settings.data_dir / "price_records.csv"
    legacy_fieldnames = [
        "price_record_id",
        "fetch_event_id",
        "observed_at",
        "source",
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
        "price_text",
        "summary",
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
                "source": "background_fetch",
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
                "price_text": "$199",
                "summary": "Legacy summary",
                "created_at": observed_at.isoformat(),
            }
        )

    saved_records = repository.load_price_records()
    assert len(saved_records) == 1
    assert saved_records[0].observed_date == observed_at.date()
