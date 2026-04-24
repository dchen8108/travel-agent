from __future__ import annotations

from datetime import date

from app.models.base import DataScope
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
