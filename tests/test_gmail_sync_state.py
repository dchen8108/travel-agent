from __future__ import annotations

from pathlib import Path

from app.models.gmail_sync_state import GmailSyncState
from app.services.gmail_sync_state import load_gmail_sync_state, save_gmail_sync_state
from app.settings import Settings


def test_gmail_sync_state_round_trips(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    state = GmailSyncState(last_history_id="12345")
    save_gmail_sync_state(settings, state)

    loaded = load_gmail_sync_state(settings)
    assert loaded.last_history_id == "12345"

