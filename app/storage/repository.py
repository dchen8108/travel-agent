from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from app.models.base import AppState
from app.models.booking import Booking
from app.models.booking_email_event import BookingEmailEvent
from app.models.price_record import PriceRecord
from app.models.route_option import RouteOption
from app.models.rule_group_target import RuleGroupTarget
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_group import TripGroup
from app.models.trip_instance import TripInstance
from app.models.trip_instance_group_membership import TripInstanceGroupMembership
from app.models.unmatched_booking import UnmatchedBooking
from app.settings import Settings
from app.storage.csv_store import load_csv_models
from app.storage.json_store import load_json_model, save_json_model
from app.storage.sqlite_store import (
    append_rows,
    connect,
    delete_rows,
    fetch_all,
    immediate_transaction,
    initialize_schema,
    replace_rows,
    upsert_rows,
)


LEGACY_CSV_MODELS: tuple[tuple[str, type], ...] = (
    ("trip_groups.csv", TripGroup),
    ("trips.csv", Trip),
    ("rule_group_targets.csv", RuleGroupTarget),
    ("route_options.csv", RouteOption),
    ("trip_instances.csv", TripInstance),
    ("trip_instance_group_memberships.csv", TripInstanceGroupMembership),
    ("trackers.csv", Tracker),
    ("tracker_fetch_targets.csv", TrackerFetchTarget),
    ("bookings.csv", Booking),
    ("unmatched_bookings.csv", UnmatchedBooking),
    ("booking_email_events.csv", BookingEmailEvent),
    ("price_records.csv", PriceRecord),
)


@dataclass
class Repository:
    settings: Settings
    _initialized: bool = field(default=False, init=False, repr=False)
    _transaction_connection: sqlite3.Connection | None = field(default=None, init=False, repr=False)

    @property
    def db_path(self) -> Path:
        return self.settings.data_dir / "travel_agent.sqlite3"

    @property
    def app_state_path(self) -> Path:
        return self.settings.config_dir / "app_state.json"

    def ensure_data_dir(self) -> None:
        if self._initialized:
            return
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.config_dir.mkdir(parents=True, exist_ok=True)
        db_exists = self.db_path.exists()
        connection = connect(self.db_path)
        try:
            initialize_schema(connection)
            db_app_state = self._load_db_app_state(connection)
        finally:
            connection.close()

        self._initialized = True
        try:
            if not db_exists and self._legacy_storage_exists():
                self._import_legacy_storage()
            elif not self.app_state_path.exists():
                self.save_app_state(db_app_state or AppState())
            if db_app_state is not None:
                self._drop_db_app_state_table()
        except Exception:
            self._initialized = False
            raise

    @contextmanager
    def transaction(self) -> Iterator[Repository]:
        self.ensure_data_dir()
        if self._transaction_connection is not None:
            yield self
            return
        connection = connect(self.db_path)
        self._transaction_connection = connection
        try:
            with immediate_transaction(connection):
                yield self
        finally:
            self._transaction_connection = None
            connection.close()

    def load_app_state(self) -> AppState:
        self.ensure_data_dir()
        return load_json_model(self.app_state_path, AppState, AppState())

    def save_app_state(self, app_state: AppState) -> None:
        self.ensure_data_dir()
        save_json_model(self.app_state_path, app_state)

    def load_trips(self) -> list[Trip]:
        return self._load_models("SELECT * FROM trips ORDER BY rowid", Trip)

    def save_trips(self, trips: list[Trip]) -> None:
        self._replace_table("trips", [item.model_dump(mode="json") for item in trips])

    def upsert_trip(self, trip: Trip) -> None:
        self._upsert_table("trips", [trip.model_dump(mode="json")], conflict_columns=("trip_id",))

    def load_trip_groups(self) -> list[TripGroup]:
        return self._load_models("SELECT * FROM trip_groups ORDER BY rowid", TripGroup)

    def save_trip_groups(self, trip_groups: list[TripGroup]) -> None:
        self._replace_table("trip_groups", [item.model_dump(mode="json") for item in trip_groups])

    def upsert_trip_group(self, trip_group: TripGroup) -> None:
        self._upsert_table("trip_groups", [trip_group.model_dump(mode="json")], conflict_columns=("trip_group_id",))

    def delete_trip_group_by_id(self, trip_group_id: str) -> None:
        self._delete_from_table(
            "trip_groups",
            where_sql="trip_group_id = ?",
            where_params=(trip_group_id,),
        )

    def load_route_options(self) -> list[RouteOption]:
        return self._load_models("SELECT * FROM route_options ORDER BY rowid", RouteOption)

    def save_route_options(self, route_options: list[RouteOption]) -> None:
        self._replace_table("route_options", [item.model_dump(mode="json") for item in route_options])

    def replace_route_options_for_trip(self, trip_id: str, route_options: list[RouteOption]) -> None:
        self.ensure_data_dir()
        rows = [item.model_dump(mode="json") for item in route_options]
        with self._borrow_connection() as (connection, own_connection):
            delete_rows(connection, "route_options", where_sql="trip_id = ?", where_params=(trip_id,))
            if rows:
                upsert_rows(connection, "route_options", rows, conflict_columns=("route_option_id",))
            if own_connection:
                connection.commit()

    def load_rule_group_targets(self) -> list[RuleGroupTarget]:
        return self._load_models("SELECT * FROM rule_group_targets ORDER BY rowid", RuleGroupTarget)

    def save_rule_group_targets(self, targets: list[RuleGroupTarget]) -> None:
        self._replace_table("rule_group_targets", [item.model_dump(mode="json") for item in targets])

    def replace_rule_group_targets_for_rule(self, rule_trip_id: str, targets: list[RuleGroupTarget]) -> None:
        self.ensure_data_dir()
        rows = [item.model_dump(mode="json") for item in targets]
        with self._borrow_connection() as (connection, own_connection):
            delete_rows(connection, "rule_group_targets", where_sql="rule_trip_id = ?", where_params=(rule_trip_id,))
            if rows:
                upsert_rows(connection, "rule_group_targets", rows, conflict_columns=("rule_trip_id", "trip_group_id"))
            if own_connection:
                connection.commit()

    def load_trip_instances(self) -> list[TripInstance]:
        return self._load_models("SELECT * FROM trip_instances ORDER BY rowid", TripInstance)

    def save_trip_instances(self, trip_instances: list[TripInstance]) -> None:
        self._replace_table("trip_instances", [item.model_dump(mode="json") for item in trip_instances])

    def load_trip_instance_group_memberships(self) -> list[TripInstanceGroupMembership]:
        return self._load_models(
            "SELECT * FROM trip_instance_group_memberships ORDER BY rowid",
            TripInstanceGroupMembership,
        )

    def save_trip_instance_group_memberships(
        self,
        memberships: list[TripInstanceGroupMembership],
    ) -> None:
        self._replace_table(
            "trip_instance_group_memberships",
            [item.model_dump(mode="json") for item in memberships],
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

    def save_trackers(self, trackers: list[Tracker]) -> None:
        self._replace_table("trackers", [item.model_dump(mode="json") for item in trackers])

    def load_tracker_fetch_targets(self) -> list[TrackerFetchTarget]:
        return self._load_models(
            "SELECT * FROM tracker_fetch_targets ORDER BY rowid",
            TrackerFetchTarget,
        )

    def load_tracker_fetch_target_ids(self) -> set[str]:
        rows = self._fetch_rows("SELECT fetch_target_id FROM tracker_fetch_targets")
        return {str(row["fetch_target_id"]) for row in rows if row.get("fetch_target_id")}

    def save_tracker_fetch_targets(self, targets: list[TrackerFetchTarget]) -> None:
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

    def load_bookings(self) -> list[Booking]:
        query = """
            SELECT
                booking_id,
                source,
                COALESCE(trip_instance_id, '') AS trip_instance_id,
                COALESCE(route_option_id, '') AS route_option_id,
                data_scope,
                airline,
                origin_airport,
                destination_airport,
                departure_date,
                departure_time,
                arrival_time,
                booked_price,
                record_locator,
                booked_at,
                booking_status AS status,
                notes,
                created_at,
                updated_at
            FROM bookings
            WHERE match_status = 'matched'
            ORDER BY rowid
        """
        return self._load_models(query, Booking)

    def save_bookings(self, bookings: list[Booking]) -> None:
        rows = [self._booking_row(booking) for booking in bookings]
        self._replace_table("bookings", rows, where_sql="match_status = 'matched'")

    def upsert_bookings(self, bookings: list[Booking]) -> None:
        rows = [self._booking_row(booking) for booking in bookings]
        self._upsert_table("bookings", rows, conflict_columns=("booking_id",))

    def delete_bookings_by_ids(self, booking_ids: list[str]) -> None:
        if not booking_ids:
            return
        placeholders = ", ".join(["?"] * len(booking_ids))
        self._delete_from_table(
            "bookings",
            where_sql=f"booking_id IN ({placeholders}) AND match_status = 'matched'",
            where_params=tuple(booking_ids),
        )

    def load_unmatched_bookings(self) -> list[UnmatchedBooking]:
        query = """
            SELECT
                booking_id AS unmatched_booking_id,
                source,
                data_scope,
                airline,
                origin_airport,
                destination_airport,
                departure_date,
                departure_time,
                arrival_time,
                booked_price,
                record_locator,
                raw_summary,
                candidate_trip_instance_ids,
                auto_link_enabled,
                resolution_status,
                created_at,
                updated_at
            FROM bookings
            WHERE match_status = 'unmatched'
            ORDER BY rowid
        """
        return self._load_models(query, UnmatchedBooking)

    def save_unmatched_bookings(self, unmatched_bookings: list[UnmatchedBooking]) -> None:
        rows = [self._unmatched_booking_row(unmatched) for unmatched in unmatched_bookings]
        self._replace_table("bookings", rows, where_sql="match_status = 'unmatched'")

    def upsert_unmatched_bookings(self, unmatched_bookings: list[UnmatchedBooking]) -> None:
        rows = [self._unmatched_booking_row(unmatched) for unmatched in unmatched_bookings]
        self._upsert_table("bookings", rows, conflict_columns=("booking_id",))

    def delete_unmatched_bookings_by_ids(self, unmatched_booking_ids: list[str]) -> None:
        if not unmatched_booking_ids:
            return
        placeholders = ", ".join(["?"] * len(unmatched_booking_ids))
        self._delete_from_table(
            "bookings",
            where_sql=f"booking_id IN ({placeholders}) AND match_status = 'unmatched'",
            where_params=tuple(unmatched_booking_ids),
        )

    def load_price_records(self) -> list[PriceRecord]:
        return self._load_models("SELECT * FROM price_records ORDER BY rowid", PriceRecord)

    def load_booking_email_events(self) -> list[BookingEmailEvent]:
        return self._load_models(
            "SELECT * FROM booking_email_events ORDER BY received_at DESC, rowid DESC",
            BookingEmailEvent,
        )

    def load_booking_email_message_ids(self) -> set[str]:
        rows = self._fetch_rows("SELECT gmail_message_id FROM booking_email_events")
        return {str(row["gmail_message_id"]) for row in rows if row.get("gmail_message_id")}

    def get_booking_email_event_by_message_id(self, gmail_message_id: str) -> BookingEmailEvent | None:
        rows = self._fetch_rows(
            "SELECT * FROM booking_email_events WHERE gmail_message_id = ? LIMIT 1",
            (gmail_message_id,),
        )
        if not rows:
            return None
        return BookingEmailEvent.model_validate(rows[0])

    def load_retryable_booking_email_events(
        self,
        *,
        max_retry_attempts: int,
        limit: int | None = None,
    ) -> list[BookingEmailEvent]:
        query = """
            SELECT *
            FROM booking_email_events
            WHERE processing_status = 'error'
              AND retryable = 1
              AND extraction_attempt_count < ?
            ORDER BY received_at ASC, rowid ASC
        """
        params: tuple[Any, ...] = (max_retry_attempts,)
        if limit is not None:
            query = f"{query}\nLIMIT ?"
            params = (max_retry_attempts, limit)
        return self._load_models(query, BookingEmailEvent, params)

    def save_booking_email_events(self, events: list[BookingEmailEvent]) -> None:
        self._replace_table(
            "booking_email_events",
            [item.model_dump(mode="json") for item in events],
        )

    def upsert_booking_email_event(self, event: BookingEmailEvent) -> None:
        self._upsert_table(
            "booking_email_events",
            [event.model_dump(mode="json")],
            conflict_columns=("email_event_id",),
        )

    def append_booking_email_events(self, events: list[BookingEmailEvent]) -> None:
        if not events:
            return
        self.ensure_data_dir()
        rows = [item.model_dump(mode="json") for item in events]
        with self._borrow_connection() as (connection, own_connection):
            append_rows(connection, "booking_email_events", rows)
            if own_connection:
                connection.commit()

    def append_price_records(self, records: list[PriceRecord]) -> None:
        if not records:
            return
        self.ensure_data_dir()
        rows = [item.model_dump(mode="json") for item in records]
        with self._borrow_connection() as (connection, own_connection):
            append_rows(connection, "price_records", rows)
            if own_connection:
                connection.commit()

    def _replace_table(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        where_sql: str | None = None,
    ) -> None:
        self.ensure_data_dir()
        with self._borrow_connection() as (connection, own_connection):
            replace_rows(connection, table, rows, where_sql=where_sql)
            if own_connection:
                connection.commit()

    def _upsert_table(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        conflict_columns: tuple[str, ...],
    ) -> None:
        if not rows:
            return
        self.ensure_data_dir()
        with self._borrow_connection() as (connection, own_connection):
            upsert_rows(connection, table, rows, conflict_columns=conflict_columns)
            if own_connection:
                connection.commit()

    def _delete_from_table(
        self,
        table: str,
        *,
        where_sql: str,
        where_params: tuple[Any, ...] = (),
    ) -> None:
        self.ensure_data_dir()
        with self._borrow_connection() as (connection, own_connection):
            delete_rows(connection, table, where_sql=where_sql, where_params=where_params)
            if own_connection:
                connection.commit()

    def _load_models(self, query: str, model_type: type, params: tuple[Any, ...] = ()) -> list:
        self.ensure_data_dir()
        rows = self._fetch_rows(query, params)
        return [model_type.model_validate(row) for row in rows]

    def _fetch_rows(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self.ensure_data_dir()
        with self._borrow_connection() as (connection, _):
            return fetch_all(connection, query, params)

    @contextmanager
    def _borrow_connection(self) -> Iterator[tuple[sqlite3.Connection, bool]]:
        if self._transaction_connection is not None:
            yield self._transaction_connection, False
            return
        connection = connect(self.db_path)
        try:
            yield connection, True
        finally:
            connection.close()

    def _legacy_storage_exists(self) -> bool:
        if (self.settings.data_dir / "app.json").exists():
            return True
        return any((self.settings.data_dir / name).exists() for name, _ in LEGACY_CSV_MODELS)

    def _import_legacy_storage(self) -> None:
        app_state = load_json_model(self.settings.data_dir / "app.json", AppState, AppState())
        legacy_rows: dict[str, list[Any]] = {
            name: load_csv_models(self.settings.data_dir / name, model_type)
            for name, model_type in LEGACY_CSV_MODELS
        }
        with self.transaction():
            self.save_trip_groups(legacy_rows["trip_groups.csv"])
            self.save_trips(legacy_rows["trips.csv"])
            self.save_rule_group_targets(legacy_rows["rule_group_targets.csv"])
            self.save_route_options(legacy_rows["route_options.csv"])
            self.save_trip_instances(legacy_rows["trip_instances.csv"])
            self.save_trip_instance_group_memberships(legacy_rows["trip_instance_group_memberships.csv"])
            self.save_trackers(legacy_rows["trackers.csv"])
            self.save_tracker_fetch_targets(legacy_rows["tracker_fetch_targets.csv"])
            self.save_bookings(legacy_rows["bookings.csv"])
            self.save_unmatched_bookings(legacy_rows["unmatched_bookings.csv"])
            self.save_booking_email_events(legacy_rows["booking_email_events.csv"])
            self.append_price_records(legacy_rows["price_records.csv"])
        self.save_app_state(app_state)

    def _load_db_app_state(self, connection: sqlite3.Connection) -> AppState | None:
        try:
            rows = fetch_all(
                connection,
                "SELECT timezone, future_weeks, enable_background_fetcher, version FROM app_state WHERE id = 1",
            )
        except sqlite3.OperationalError:
            return None
        if not rows:
            return None
        return AppState.model_validate(rows[0])

    def _drop_db_app_state_table(self) -> None:
        with self._borrow_connection() as (connection, own_connection):
            connection.execute("DROP TABLE IF EXISTS app_state")
            if own_connection:
                connection.commit()

    @staticmethod
    def _booking_row(booking: Booking) -> dict[str, Any]:
        return {
            "booking_id": booking.booking_id,
            "source": booking.source,
            "trip_instance_id": booking.trip_instance_id,
            "route_option_id": booking.route_option_id,
            "data_scope": booking.data_scope,
            "airline": booking.airline,
            "origin_airport": booking.origin_airport,
            "destination_airport": booking.destination_airport,
            "departure_date": booking.departure_date.isoformat(),
            "departure_time": booking.departure_time,
            "arrival_time": booking.arrival_time,
            "booked_price": float(booking.booked_price),
            "record_locator": booking.record_locator,
            "booked_at": booking.booked_at.isoformat(),
            "booking_status": booking.status,
            "match_status": "matched",
            "raw_summary": "",
            "candidate_trip_instance_ids": "",
            "auto_link_enabled": True,
            "resolution_status": "resolved",
            "notes": booking.notes,
            "created_at": booking.created_at.isoformat(),
            "updated_at": booking.updated_at.isoformat(),
        }

    @staticmethod
    def _unmatched_booking_row(unmatched: UnmatchedBooking) -> dict[str, Any]:
        return {
            "booking_id": unmatched.unmatched_booking_id,
            "source": unmatched.source,
            "data_scope": unmatched.data_scope,
            "trip_instance_id": None,
            "route_option_id": "",
            "airline": unmatched.airline,
            "origin_airport": unmatched.origin_airport,
            "destination_airport": unmatched.destination_airport,
            "departure_date": unmatched.departure_date.isoformat(),
            "departure_time": unmatched.departure_time,
            "arrival_time": unmatched.arrival_time,
            "booked_price": float(unmatched.booked_price),
            "record_locator": unmatched.record_locator,
            "booked_at": unmatched.created_at.isoformat(),
            "booking_status": "active",
            "match_status": "unmatched",
            "raw_summary": unmatched.raw_summary,
            "candidate_trip_instance_ids": unmatched.candidate_trip_instance_ids,
            "auto_link_enabled": unmatched.auto_link_enabled,
            "resolution_status": unmatched.resolution_status,
            "notes": "",
            "created_at": unmatched.created_at.isoformat(),
            "updated_at": unmatched.updated_at.isoformat(),
        }
