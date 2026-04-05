from __future__ import annotations

from app.models.rule_group_target import RuleGroupTarget
from app.models.trip_group import TripGroup
from app.storage.sqlite_store import delete_rows, upsert_rows


class GroupsRepositoryMixin:
    def load_trip_groups(self) -> list[TripGroup]:
        return self._load_models("SELECT * FROM trip_groups ORDER BY rowid", TripGroup)

    def upsert_trip_group(self, trip_group: TripGroup) -> None:
        self._upsert_table("trip_groups", [trip_group.model_dump(mode="json")], conflict_columns=("trip_group_id",))

    def delete_trip_group_by_id(self, trip_group_id: str) -> None:
        self._delete_from_table(
            "trip_groups",
            where_sql="trip_group_id = ?",
            where_params=(trip_group_id,),
        )

    def load_rule_group_targets(self) -> list[RuleGroupTarget]:
        return self._load_models("SELECT * FROM rule_group_targets ORDER BY rowid", RuleGroupTarget)

    def replace_rule_group_targets_for_rule(self, rule_trip_id: str, targets: list[RuleGroupTarget]) -> None:
        self.ensure_data_dir()
        rows = [item.model_dump(mode="json") for item in targets]
        with self._borrow_connection() as (connection, own_connection):
            delete_rows(connection, "rule_group_targets", where_sql="rule_trip_id = ?", where_params=(rule_trip_id,))
            if rows:
                upsert_rows(connection, "rule_group_targets", rows, conflict_columns=("rule_trip_id", "trip_group_id"))
            if own_connection:
                connection.commit()
