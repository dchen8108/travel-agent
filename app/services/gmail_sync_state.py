from __future__ import annotations

from pathlib import Path

from app.models.gmail_sync_state import GmailSyncState
from app.settings import Settings
from app.storage.json_store import load_json_model, save_json_model


def gmail_sync_state_path(settings: Settings) -> Path:
    return settings.config_local_dir / "gmail_sync_state.json"


def load_gmail_sync_state(settings: Settings) -> GmailSyncState:
    return load_json_model(
        gmail_sync_state_path(settings),
        GmailSyncState,
        GmailSyncState(),
    )


def save_gmail_sync_state(settings: Settings, state: GmailSyncState) -> None:
    save_json_model(gmail_sync_state_path(settings), state)

