from __future__ import annotations

from pathlib import Path

from app.models.gmail_integration import GmailIntegrationConfig
from app.settings import Settings
from app.storage.json_store import load_json_model


def gmail_integration_config_path(settings: Settings) -> Path:
    return settings.config_dir / "gmail_integration.json"


def load_gmail_integration_config(settings: Settings) -> GmailIntegrationConfig:
    return load_json_model(
        gmail_integration_config_path(settings),
        GmailIntegrationConfig,
        GmailIntegrationConfig(),
    )

