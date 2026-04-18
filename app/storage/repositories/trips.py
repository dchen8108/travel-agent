from __future__ import annotations

from app.models.route_option import RouteOption
from app.models.trip import Trip
from app.storage.sqlite_store import delete_rows, upsert_rows


class TripsRepositoryMixin:
    def load_trips(self) -> list[Trip]:
        return self._load_models("SELECT * FROM trips ORDER BY rowid", Trip)

    def upsert_trip(self, trip: Trip) -> None:
        self._upsert_table("trips", [trip.model_dump(mode="json")], conflict_columns=("trip_id",))

    def load_route_options(self) -> list[RouteOption]:
        return self._load_models("SELECT * FROM route_options ORDER BY rowid", RouteOption)

    def replace_route_options_for_trip(self, trip_id: str, route_options: list[RouteOption]) -> None:
        self.ensure_data_dir()
        rows = [item.model_dump(mode="json", by_alias=True) for item in route_options]
        with self._borrow_connection() as (connection, own_connection):
            delete_rows(connection, "route_options", where_sql="trip_id = ?", where_params=(trip_id,))
            if rows:
                upsert_rows(connection, "route_options", rows, conflict_columns=("route_option_id",))
            if own_connection:
                connection.commit()
