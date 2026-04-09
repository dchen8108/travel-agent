from __future__ import annotations

import json
from pathlib import Path

from app.models.gmail_integration import GmailIntegrationConfig
from app.settings import Settings


def gmail_integration_config_path(settings: Settings) -> Path:
    return settings.config_dir / "gmail_integration.json"


def gmail_local_integration_config_path(settings: Settings) -> Path:
    return settings.config_local_dir / "gmail_integration.json"


def _load_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def load_gmail_integration_config(settings: Settings) -> GmailIntegrationConfig:
    payload = {
        **_load_json_object(gmail_integration_config_path(settings)),
        **_load_json_object(gmail_local_integration_config_path(settings)),
    }
    if not payload:
        return GmailIntegrationConfig()
    return GmailIntegrationConfig.model_validate(payload)
