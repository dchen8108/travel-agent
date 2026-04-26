from __future__ import annotations

from datetime import date

from app.models.base import DataScope
from app.services.bookings import BookingCandidate, record_booking
from app.services.dashboard_snapshot import load_persisted_snapshot
from app.services.frontend_api import trip_editor_payload_for_new
from app.services.groups import save_trip_group
from app.services.snapshot_queries import groups_for_trip
from app.services.trip_editor import TripSaveInput, save_trip_workflow
from app.storage.repository import Repository


def test_save_trip_workflow_refreshes_one_time_snapshot_after_manual_group_updates(
    repository: Repository,
) -> None:
    group = save_trip_group(repository, trip_group_id=None, label="Commute")

    result = save_trip_workflow(
        repository,
        data=TripSaveInput(
            trip_id=None,
            label="One-off commute",
            trip_kind="one_time",
            trip_group_ids=[group.trip_group_id],
            preference_mode="equal",
            anchor_date=date(2026, 4, 20),
            anchor_weekday="Monday",
            route_options=[
                {
                    "origin_airports": "LAX",
                    "destination_airports": "SFO",
                    "airlines": "Southwest",
                    "day_offset": 0,
                    "start_time": "06:00",
                    "end_time": "08:00",
                    "fare_class": "basic_economy",
                    "savings_needed_vs_previous": 0,
                }
            ],
            data_scope=DataScope.LIVE,
        ),
    )

    assert [item.trip_group_id for item in groups_for_trip(result.snapshot, result.trip)] == [group.trip_group_id]
    assert any(item.trip_group_id == group.trip_group_id for item in repository.load_trip_instance_group_memberships())


def test_save_trip_workflow_links_prefilled_unmatched_booking_with_basic_economy_and_stops(
    repository: Repository,
) -> None:
    booking, unmatched = record_booking(
        repository,
        BookingCandidate(
            airline="Alaska",
            origin_airport="ANC",
            destination_airport="BUR",
            departure_date=date(2026, 6, 1),
            departure_time="11:12",
            arrival_time="19:34",
            arrival_day_offset=0,
            fare_class="basic_economy",
            stops="1_stop",
            flight_number="AS 1484, AS 530",
            booked_price=0,
            record_locator="WUYQTV",
        ),
    )
    assert booking is None
    assert unmatched is not None

    payload = trip_editor_payload_for_new(
        load_persisted_snapshot(repository),
        trip_kind="one_time",
        trip_group_id="",
        unmatched_booking_id=unmatched.unmatched_booking_id,
        trip_label="Anchorage Return",
    )

    result = save_trip_workflow(
        repository,
        data=TripSaveInput(
            trip_id=None,
            label=str(payload["values"]["label"]),
            trip_kind=str(payload["values"]["tripKind"]),
            trip_group_ids=list(payload["values"]["tripGroupIds"]),
            preference_mode=str(payload["values"]["preferenceMode"]),
            anchor_date=date.fromisoformat(str(payload["values"]["anchorDate"])),
            anchor_weekday=str(payload["values"]["anchorWeekday"]),
            route_options=[
                {
                    "route_option_id": "",
                    "savings_needed_vs_previous": 0,
                    "origin_airports": "ANC",
                    "destination_airports": "BUR",
                    "airlines": "Alaska",
                    "stops": "1_stop",
                    "day_offset": 0,
                    "start_time": "10:12",
                    "end_time": "13:12",
                    "fare_class": "basic_economy",
                }
            ],
            data_scope=str(payload["values"]["dataScope"]),
            source_unmatched_booking_id=unmatched.unmatched_booking_id,
        ),
    )

    assert result.linked_booking_id
    assert "panel=bookings" in result.redirect_to

    stored_booking = next(item for item in repository.load_bookings() if item.booking_id == result.linked_booking_id)
    assert stored_booking.trip_instance_id
    assert stored_booking.route_option_id
    assert repository.load_unmatched_bookings() == []
