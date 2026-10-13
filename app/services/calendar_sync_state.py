from __future__ import annotations

from pathlib import Path

from app.models.calendar_sync_state import CalendarSyncState
from app.settings import Settings
from app.storage.json_store import load_json_model, save_json_model


def calendar_sync_state_path(settings: Settings) -> Path:
    return settings.config_local_dir / "calendar_sync_state.json"


def load_calendar_sync_state(settings: Settings) -> CalendarSyncState:
    return load_json_model(
        calendar_sync_state_path(settings),
        CalendarSyncState,
        CalendarSyncState(),
    )


def save_calendar_sync_state(settings: Settings, state: CalendarSyncState) -> None:
    save_json_model(calendar_sync_state_path(settings), state)
