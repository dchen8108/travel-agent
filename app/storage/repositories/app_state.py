from __future__ import annotations

from app.models.base import AppState
from app.storage.json_store import load_json_model, save_json_model


class AppStateRepositoryMixin:
    def load_app_state(self) -> AppState:
        self.ensure_data_dir()
        return load_json_model(self.app_state_path, AppState, AppState())

    def save_app_state(self, app_state: AppState) -> None:
        self.ensure_data_dir()
        save_json_model(self.app_state_path, app_state)
