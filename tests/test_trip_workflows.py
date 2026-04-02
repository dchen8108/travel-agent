from __future__ import annotations

from base64 import urlsafe_b64decode
from datetime import date
from urllib.parse import parse_qs, urlsplit

from app.services.google_flights import build_google_flights_query_url
from app.services.dashboard import archived_one_time_trips, horizon_instances_for_trip, past_instances_for_trip, scheduled_instances
from app.services.trip_instances import delete_generated_trip_instance, detach_generated_trip_instance
from app.services.trips import delete_trip, save_past_trip, save_trip, set_trip_active
from app.services.workflows import sync_and_persist
from app.storage.repository import Repository


def _read_varint(buffer: bytes, index: int) -> tuple[int, int]:
    shift = 0
    value = 0
    while True:
        byte = buffer[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return value, index
        shift += 7


def _parse_fields(buffer: bytes) -> list[tuple[int, int, object]]:
    index = 0
    items: list[tuple[int, int, object]] = []
    while index < len(buffer):
        key, index = _read_varint(buffer, index)
        field_number = key >> 3
        wire_type = key & 0x07
        if wire_type == 0:
            value, index = _read_varint(buffer, index)
            items.append((field_number, wire_type, value))
        elif wire_type == 2:
            length, index = _read_varint(buffer, index)
            payload = buffer[index:index + length]
            index += length
            items.append((field_number, wire_type, payload))
        else:
            raise AssertionError(f"Unsupported wire type {wire_type}")
    return items


def _decode_tfs(url: str) -> list[tuple[int, int, object]]:
    query = parse_qs(urlsplit(url).query)
    tfs = query["tfs"][0]
    padded = tfs + "=" * ((4 - len(tfs) % 4) % 4)
    return _parse_fields(urlsafe_b64decode(padded))


def test_weekly_trip_generates_twelve_future_instances(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="LA to SF Outbound",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX",
                "destination_airports": "SFO",
                "airlines": "Alaska|United",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 3, 31))
    trip_instances = [item for item in snapshot.trip_instances if item.trip_id == trip.trip_id]

    assert len(trip_instances) == 12
    assert trip_instances[0].anchor_date == date(2026, 4, 6)
    assert all(instance.display_label.startswith("LA to SF Outbound") for instance in trip_instances)
    assert all(instance.instance_kind == "generated" for instance in trip_instances)
    assert len([tracker for tracker in snapshot.trackers if tracker.trip_instance_id == trip_instances[0].trip_instance_id]) == 1


def test_skipped_occurrence_survives_reconciliation(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="SF to LA Return",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Wednesday",
        route_option_payloads=[
            {
                "origin_airports": "SFO",
                "destination_airports": "BUR|LAX",
                "airlines": "Alaska",
                "day_offset": 0,
                "start_time": "17:00",
                "end_time": "22:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 3, 31))
    trip_instance = next(item for item in snapshot.trip_instances if item.trip_id == trip.trip_id)
    trip_instance.travel_state = "skipped"
    repository.save_trip_instances(snapshot.trip_instances)

    refreshed = sync_and_persist(repository, today=date(2026, 4, 2))
    same_instance = next(item for item in refreshed.trip_instances if item.trip_instance_id == trip_instance.trip_instance_id)
    assert same_instance.travel_state == "skipped"


def test_deactivating_weekly_trip_preserves_existing_instances_without_growing_frontier(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="LA to SF Weekly",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX",
                "destination_airports": "SFO",
                "airlines": "Alaska|United",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    initial = sync_and_persist(repository, today=date(2026, 3, 31))
    initial_instances = [item for item in initial.trip_instances if item.trip_id == trip.trip_id]
    initial_dates = [item.anchor_date for item in initial_instances]
    initial_tracker_ids = {
        tracker.tracker_id
        for tracker in initial.trackers
        if any(instance.trip_instance_id == tracker.trip_instance_id for instance in initial_instances)
    }
    assert len(initial_dates) == 12

    set_trip_active(repository, trip.trip_id, False)
    paused = sync_and_persist(repository, today=date(2026, 4, 21))
    paused_instances = [item for item in paused.trip_instances if item.trip_id == trip.trip_id]
    paused_dates = [item.anchor_date for item in paused_instances]
    paused_tracker_ids = {
        tracker.tracker_id
        for tracker in paused.trackers
        if any(instance.trip_instance_id == tracker.trip_instance_id for instance in paused_instances)
    }

    assert paused_dates == initial_dates
    assert paused_tracker_ids == initial_tracker_ids
    assert all(instance.instance_kind == "generated" for instance in paused_instances)


def test_one_time_trip_labels_can_repeat_on_different_dates(repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Conference Arrival",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 10),
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

    duplicate = save_trip(
        repository,
        trip_id=None,
        label="Conference Arrival",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 12),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "SEA",
                "destination_airports": "LAX",
                "airlines": "Delta",
                "day_offset": 0,
                "start_time": "12:00",
                "end_time": "16:00",
            }
        ],
    )

    assert duplicate.label == "Conference Arrival"


def test_one_time_trip_label_and_date_must_be_unique(repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Conference Arrival",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 10),
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

    try:
        save_trip(
            repository,
            trip_id=None,
            label="Conference Arrival",
            trip_kind="one_time",
            active=True,
            anchor_date=date(2026, 5, 10),
            anchor_weekday="",
            route_option_payloads=[
                {
                    "origin_airports": "SEA",
                    "destination_airports": "LAX",
                    "airlines": "Delta",
                    "day_offset": 0,
                    "start_time": "12:00",
                    "end_time": "16:00",
                }
            ],
        )
    except ValueError as exc:
        assert str(exc) == "A one-time trip with this Trip Label and date already exists."
    else:
        raise AssertionError("Expected one-time label/date collision to raise.")


def test_recurring_trip_labels_must_stay_unique(repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Work Commute",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
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

    try:
        save_trip(
            repository,
            trip_id=None,
            label="Work Commute",
            trip_kind="weekly",
            active=True,
            anchor_date=None,
            anchor_weekday="Tuesday",
            route_option_payloads=[
                {
                    "origin_airports": "SFO",
                    "destination_airports": "BUR",
                    "airlines": "Alaska",
                    "day_offset": 0,
                    "start_time": "15:00",
                    "end_time": "20:00",
                }
            ],
        )
    except ValueError as exc:
        assert str(exc) == "Recurring trips must use a unique Trip Label."
    else:
        raise AssertionError("Expected duplicate recurring trip label to raise.")


def test_one_time_trip_cannot_reuse_recurring_trip_label(repository: Repository) -> None:
    save_trip(
        repository,
        trip_id=None,
        label="Work Commute",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
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

    try:
        save_trip(
            repository,
            trip_id=None,
            label="Work Commute",
            trip_kind="one_time",
            active=True,
            anchor_date=date(2026, 5, 10),
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
    except ValueError as exc:
        assert str(exc) == "This Trip Label is already used by a recurring trip."
    else:
        raise AssertionError("Expected recurring trip label collision to raise.")


def test_deleted_one_time_trip_no_longer_blocks_same_label_and_date(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Conference Arrival",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 10),
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
    delete_trip(repository, trip.trip_id)

    replacement = save_trip(
        repository,
        trip_id=None,
        label="Conference Arrival",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "SEA",
                "destination_airports": "LAX",
                "airlines": "Delta",
                "day_offset": 0,
                "start_time": "12:00",
                "end_time": "16:00",
            }
        ],
    )

    assert replacement.trip_id != trip.trip_id


def test_one_time_trip_creates_a_standalone_instance(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Conference Arrival",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 10),
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

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instances = [item for item in snapshot.trip_instances if item.trip_id == trip.trip_id]

    assert len(trip_instances) == 1
    assert trip_instances[0].display_label == "Conference Arrival"
    assert trip_instances[0].instance_kind == "standalone"


def test_archived_one_time_trip_is_hidden_from_active_scheduled_views(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Archive Me",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 10),
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

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    assert len(scheduled_instances(snapshot, today=date(2026, 4, 1))) == 1

    set_trip_active(repository, trip.trip_id, False)
    archived = sync_and_persist(repository, today=date(2026, 4, 1))

    assert not scheduled_instances(archived, today=date(2026, 4, 1))
    assert [item.trip_id for item in archived_one_time_trips(archived)] == [trip.trip_id]


def test_archived_one_time_trip_shuts_down_tracking_until_restored(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Archive Tracking Shutdown",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 10),
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

    active_snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    active_instance_ids = {
        item.trip_instance_id for item in active_snapshot.trip_instances if item.trip_id == trip.trip_id
    }
    assert any(tracker.trip_instance_id in active_instance_ids for tracker in active_snapshot.trackers)
    assert any(target.trip_instance_id in active_instance_ids for target in active_snapshot.tracker_fetch_targets)

    set_trip_active(repository, trip.trip_id, False)
    archived_snapshot = sync_and_persist(repository, today=date(2026, 4, 1))

    assert not any(tracker.trip_instance_id in active_instance_ids for tracker in archived_snapshot.trackers)
    assert not any(target.trip_instance_id in active_instance_ids for target in archived_snapshot.tracker_fetch_targets)

    set_trip_active(repository, trip.trip_id, True)
    restored_snapshot = sync_and_persist(repository, today=date(2026, 4, 1))

    assert any(tracker.trip_instance_id in active_instance_ids for tracker in restored_snapshot.trackers)
    assert any(target.trip_instance_id in active_instance_ids for target in restored_snapshot.tracker_fetch_targets)


def test_recurring_trip_keeps_past_instances_but_horizon_only_shows_future(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Weekly Commute History",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
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

    sync_and_persist(repository, today=date(2026, 3, 24))
    snapshot = sync_and_persist(repository, today=date(2026, 3, 31))

    trip_instances = [item for item in snapshot.trip_instances if item.trip_id == trip.trip_id]
    assert len(trip_instances) == 13
    assert len(horizon_instances_for_trip(snapshot, trip.trip_id, today=date(2026, 3, 31))) == 12
    assert len(past_instances_for_trip(snapshot, trip.trip_id, today=date(2026, 3, 31))) == 1


def test_weekly_trip_auto_provisions_a_group(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Weekly Grouped Commute",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
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

    groups = repository.load_trip_groups()
    assert trip.trip_group_id
    assert len(groups) == 1
    assert groups[0].trip_group_id == trip.trip_group_id
    assert groups[0].label == trip.label


def test_detaching_generated_trip_instance_preserves_occurrence_and_group(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Detach Commute",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
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

    initial = sync_and_persist(repository, today=date(2026, 3, 31))
    generated = next(item for item in initial.trip_instances if item.trip_id == trip.trip_id)
    detached = detach_generated_trip_instance(repository, generated.trip_instance_id)

    refreshed = sync_and_persist(repository, today=date(2026, 3, 31))
    same_instance = next(item for item in refreshed.trip_instances if item.trip_instance_id == generated.trip_instance_id)
    detached_trip = next(item for item in refreshed.trips if item.trip_id == same_instance.trip_id)
    matching_occurrences = [
        item
        for item in refreshed.trip_instances
        if item.recurring_rule_trip_id == trip.trip_id and item.rule_occurrence_date == generated.anchor_date and not item.deleted
    ]

    assert same_instance.trip_instance_id == generated.trip_instance_id
    assert same_instance.inheritance_mode == "detached"
    assert same_instance.instance_kind == "standalone"
    assert same_instance.trip_id != trip.trip_id
    assert detached_trip.trip_kind == "one_time"
    assert detached_trip.trip_group_id == trip.trip_group_id
    assert len(matching_occurrences) == 1


def test_deleting_generated_trip_instance_tombstones_and_suppresses_regeneration(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Delete Generated Commute",
        trip_kind="weekly",
        active=True,
        anchor_date=None,
        anchor_weekday="Monday",
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

    initial = sync_and_persist(repository, today=date(2026, 3, 31))
    generated = next(item for item in initial.trip_instances if item.trip_id == trip.trip_id)
    delete_generated_trip_instance(repository, generated.trip_instance_id)

    refreshed = sync_and_persist(repository, today=date(2026, 3, 31))
    same_instance = next(item for item in refreshed.trip_instances if item.trip_instance_id == generated.trip_instance_id)

    assert same_instance.deleted is True
    assert not any(tracker.trip_instance_id == generated.trip_instance_id for tracker in refreshed.trackers)
    assert not any(target.trip_instance_id == generated.trip_instance_id for target in refreshed.tracker_fetch_targets)
    assert len(
        [
            item
            for item in refreshed.trip_instances
            if item.recurring_rule_trip_id == trip.trip_id and item.rule_occurrence_date == generated.anchor_date
        ]
    ) == 1


def test_save_past_trip_creates_historical_instance_without_trackers(repository: Repository) -> None:
    trip = save_past_trip(
        repository,
        trip_id=None,
        label="Old conference hop",
        anchor_date=date(2026, 3, 10),
    )

    snapshot = sync_and_persist(repository, today=date(2026, 3, 31))
    trip_instances = [item for item in snapshot.trip_instances if item.trip_id == trip.trip_id]
    trackers = [item for item in snapshot.trackers if item.trip_instance_id in {instance.trip_instance_id for instance in trip_instances}]

    assert len(trip_instances) == 1
    assert trip_instances[0].display_label == "Old conference hop"
    assert trip_instances[0].instance_kind == "standalone"
    assert trip_instances[0].anchor_date == date(2026, 3, 10)
    assert len(trackers) == 0


def test_generated_google_flights_url_uses_structured_tfs_query(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Seed search test",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 5, 10),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "BUR|LAX",
                "destination_airports": "SFO|OAK",
                "airlines": "Alaska|United",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "10:00",
            }
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance = next(item for item in snapshot.trip_instances if item.trip_id == trip.trip_id)
    tracker = next(item for item in snapshot.trackers if item.trip_instance_id == trip_instance.trip_instance_id)

    url = build_google_flights_query_url(tracker)
    query = parse_qs(urlsplit(url).query)
    top_fields = _decode_tfs(url)
    flight_data = next(value for field, wire, value in top_fields if field == 3 and wire == 2)
    nested_fields = _parse_fields(flight_data)  # type: ignore[arg-type]

    assert url.startswith("https://www.google.com/travel/flights/search?")
    assert query["hl"] == ["en-US"]
    assert query["tfu"] == ["EgYIABAAGAA"]
    assert any(field == 1 and value == 28 for field, wire, value in top_fields if wire == 0)
    assert any(field == 2 and value == 2 for field, wire, value in top_fields if wire == 0)
    assert any(field == 14 and value == 1 for field, wire, value in top_fields if wire == 0)
    assert any(field == 16 for field, wire, value in top_fields if wire == 2)
    assert any(field == 8 and value == 6 for field, wire, value in nested_fields if wire == 0)
    assert any(field == 9 and value == 9 for field, wire, value in nested_fields if wire == 0)
    assert any(field == 10 and value == 0 for field, wire, value in nested_fields if wire == 0)
    assert any(field == 11 and value == 23 for field, wire, value in nested_fields if wire == 0)


def test_route_option_fare_class_policy_persists_to_trackers(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Fare Policy Trip",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 13),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "Alaska|Southwest",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "08:00",
                "fare_class_policy": "exclude_basic",
            }
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    route_option = next(item for item in snapshot.route_options if item.trip_id == trip.trip_id)
    trip_instance = next(item for item in snapshot.trip_instances if item.trip_id == trip.trip_id)
    tracker = next(item for item in snapshot.trackers if item.trip_instance_id == trip_instance.trip_instance_id)

    assert route_option.fare_class_policy == "exclude_basic"
    assert tracker.fare_class_policy == "exclude_basic"


def test_generated_google_flights_url_can_exclude_basic_economy(repository: Repository) -> None:
    trip = save_trip(
        repository,
        trip_id=None,
        label="Exclude Basic Trip",
        trip_kind="one_time",
        active=True,
        anchor_date=date(2026, 4, 13),
        anchor_weekday="",
        route_option_payloads=[
            {
                "origin_airports": "LAX",
                "destination_airports": "SFO",
                "airlines": "Alaska|Southwest",
                "day_offset": 0,
                "start_time": "06:00",
                "end_time": "08:00",
                "fare_class_policy": "exclude_basic",
            }
        ],
    )

    snapshot = sync_and_persist(repository, today=date(2026, 4, 1))
    trip_instance = next(item for item in snapshot.trip_instances if item.trip_id == trip.trip_id)
    tracker = next(item for item in snapshot.trackers if item.trip_instance_id == trip_instance.trip_instance_id)

    url = build_google_flights_query_url(tracker)
    query = parse_qs(urlsplit(url).query)
    top_fields = _decode_tfs(url)

    assert query["hl"] == ["en-US"]
    assert query["tfu"] == ["EgYIABAAGAA"]
    assert any(field == 25 and value == 1 for field, wire, value in top_fields if wire == 0)
