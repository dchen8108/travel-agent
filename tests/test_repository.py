from __future__ import annotations

import sqlite3
from pathlib import Path

from app.models.base import AppState
from app.settings import Settings
from app.storage.repository import Repository


def test_repository_stores_app_state_in_config_json(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    repository = Repository(settings)
    repository.ensure_data_dir()
    app_state = AppState(
        timezone="America/New_York",
        future_weeks=16,
        enable_background_fetcher=False,
        version=5,
    )

    repository.save_app_state(app_state)

    assert repository.app_state_path.exists()
    assert repository.load_app_state() == app_state

    connection = sqlite3.connect(repository.db_path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        connection.close()
    assert "app_state" not in tables


def test_repository_bootstraps_app_state_from_existing_db_row_when_config_missing(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.data_dir / "travel_agent.sqlite3")
    try:
        connection.execute(
            """
            CREATE TABLE app_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                timezone TEXT NOT NULL,
                future_weeks INTEGER NOT NULL,
                enable_background_fetcher INTEGER NOT NULL,
                version INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO app_state (id, timezone, future_weeks, enable_background_fetcher, version)
            VALUES (1, 'America/Chicago', 9, 0, 4)
            """
        )
        connection.commit()
    finally:
        connection.close()

    repository = Repository(settings)
    repository.ensure_data_dir()

    assert repository.load_app_state() == AppState(
        timezone="America/Chicago",
        future_weeks=9,
        enable_background_fetcher=False,
        version=4,
    )
    assert repository.app_state_path.exists()

    connection = sqlite3.connect(repository.db_path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        connection.close()
    assert "app_state" not in tables
