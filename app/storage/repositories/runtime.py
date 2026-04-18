from __future__ import annotations

from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip_instance import TripInstance
from app.models.trip_instance_group_membership import TripInstanceGroupMembership
from app.storage.sqlite_store import delete_rows, upsert_rows


class RuntimeRepositoryMixin:
    def load_trip_instances(self) -> list[TripInstance]:
        return self._load_models("SELECT * FROM trip_instances ORDER BY rowid", TripInstance)

    def replace_trip_instances(self, trip_instances: list[TripInstance]) -> None:
        self._replace_table("trip_instances", [item.model_dump(mode="json") for item in trip_instances])

    def upsert_trip_instances(self, trip_instances: list[TripInstance]) -> None:
        self._upsert_table(
            "trip_instances",
            [item.model_dump(mode="json") for item in trip_instances],
            conflict_columns=("trip_instance_id",),
        )

    def delete_trip_instances_by_ids(self, trip_instance_ids: list[str]) -> None:
        if not trip_instance_ids:
            return
        placeholders = ", ".join(["?"] * len(trip_instance_ids))
        self._delete_from_table(
            "trip_instances",
            where_sql=f"trip_instance_id IN ({placeholders})",
            where_params=tuple(trip_instance_ids),
        )

    def load_trip_instance_group_memberships(self) -> list[TripInstanceGroupMembership]:
        return self._load_models(
            "SELECT * FROM trip_instance_group_memberships ORDER BY rowid",
            TripInstanceGroupMembership,
        )

    def replace_trip_instance_group_memberships(
        self,
        memberships: list[TripInstanceGroupMembership],
    ) -> None:
        self._replace_table(
            "trip_instance_group_memberships",
            [item.model_dump(mode="json") for item in memberships],
        )

    def upsert_trip_instance_group_memberships(
        self,
        memberships: list[TripInstanceGroupMembership],
    ) -> None:
        self._upsert_table(
            "trip_instance_group_memberships",
            [item.model_dump(mode="json") for item in memberships],
            conflict_columns=("trip_instance_id", "trip_group_id"),
        )

    def delete_trip_instance_group_memberships_by_keys(
        self,
        membership_keys: list[tuple[str, str]],
    ) -> None:
        if not membership_keys:
            return
        clauses = ["(trip_instance_id = ? AND trip_group_id = ?)"] * len(membership_keys)
        params = tuple(value for pair in membership_keys for value in pair)
        self._delete_from_table(
            "trip_instance_group_memberships",
            where_sql=" OR ".join(clauses),
            where_params=params,
        )

    def replace_trip_instance_group_memberships_for_instance(
        self,
        trip_instance_id: str,
        memberships: list[TripInstanceGroupMembership],
    ) -> None:
        self.ensure_data_dir()
        rows = [item.model_dump(mode="json") for item in memberships]
        with self._borrow_connection() as (connection, own_connection):
            delete_rows(
                connection,
                "trip_instance_group_memberships",
                where_sql="trip_instance_id = ?",
                where_params=(trip_instance_id,),
            )
            if rows:
                upsert_rows(
                    connection,
                    "trip_instance_group_memberships",
                    rows,
                    conflict_columns=("trip_instance_id", "trip_group_id"),
                )
            if own_connection:
                connection.commit()

    def delete_trip_instance_group_memberships_by_group_id(self, trip_group_id: str) -> None:
        self._delete_from_table(
            "trip_instance_group_memberships",
            where_sql="trip_group_id = ?",
            where_params=(trip_group_id,),
        )

    def load_trackers(self) -> list[Tracker]:
        return self._load_models("SELECT * FROM trackers ORDER BY rowid", Tracker)

    def replace_trackers(self, trackers: list[Tracker]) -> None:
        self._replace_table("trackers", [item.model_dump(mode="json", by_alias=True) for item in trackers])

    def upsert_trackers(self, trackers: list[Tracker]) -> None:
        self._upsert_table(
            "trackers",
            [item.model_dump(mode="json", by_alias=True) for item in trackers],
            conflict_columns=("tracker_id",),
        )

    def delete_trackers_by_ids(self, tracker_ids: list[str]) -> None:
        if not tracker_ids:
            return
        placeholders = ", ".join(["?"] * len(tracker_ids))
        self._delete_from_table(
            "trackers",
            where_sql=f"tracker_id IN ({placeholders})",
            where_params=tuple(tracker_ids),
        )

    def load_tracker_fetch_targets(self) -> list[TrackerFetchTarget]:
        return self._load_models(
            "SELECT * FROM tracker_fetch_targets ORDER BY rowid",
            TrackerFetchTarget,
        )

    def load_tracker_fetch_target_ids(self) -> set[str]:
        rows = self._fetch_rows("SELECT fetch_target_id FROM tracker_fetch_targets")
        return {str(row["fetch_target_id"]) for row in rows if row.get("fetch_target_id")}

    def replace_tracker_fetch_targets(self, targets: list[TrackerFetchTarget]) -> None:
        self._replace_table(
            "tracker_fetch_targets",
            [item.model_dump(mode="json") for item in targets],
        )

    def upsert_tracker_fetch_targets(self, targets: list[TrackerFetchTarget]) -> None:
        self._upsert_table(
            "tracker_fetch_targets",
            [item.model_dump(mode="json") for item in targets],
            conflict_columns=("fetch_target_id",),
        )

    def delete_tracker_fetch_targets_by_ids(self, fetch_target_ids: list[str]) -> None:
        if not fetch_target_ids:
            return
        placeholders = ", ".join(["?"] * len(fetch_target_ids))
        self._delete_from_table(
            "tracker_fetch_targets",
            where_sql=f"fetch_target_id IN ({placeholders})",
            where_params=tuple(fetch_target_ids),
        )
