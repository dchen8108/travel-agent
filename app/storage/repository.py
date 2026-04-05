from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from app.models.base import AppState
from app.settings import Settings
from app.storage.repositories import (
    AppStateRepositoryMixin,
    BookingsRepositoryMixin,
    GroupsRepositoryMixin,
    IngestionRepositoryMixin,
    RuntimeRepositoryMixin,
    TripsRepositoryMixin,
)
from app.storage.sqlite_store import (
    connect,
    delete_rows,
    fetch_all,
    immediate_transaction,
    initialize_schema,
    replace_rows,
    upsert_rows,
)


@dataclass
class Repository(
    AppStateRepositoryMixin,
    TripsRepositoryMixin,
    GroupsRepositoryMixin,
    RuntimeRepositoryMixin,
    BookingsRepositoryMixin,
    IngestionRepositoryMixin,
):
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
        connection = connect(self.db_path)
        try:
            initialize_schema(connection)
        finally:
            connection.close()

        self._initialized = True
        try:
            if not self.app_state_path.exists():
                self.save_app_state(AppState())
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
