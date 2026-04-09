from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.gmail_integration import GmailIntegrationConfig
from app.services.gmail_config import load_gmail_integration_config
from app.settings import Settings


def test_load_gmail_integration_config_reads_checked_in_shape(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": True,
        "allowed_from_addresses": ["Travel Bot <alerts@example.com>", "alerts@example.com"],
        "max_messages_per_poll": 11,
        "launchd_poll_interval_seconds": 240,
        "launchd_max_messages": 7,
    }
    (settings.config_dir / "gmail_integration.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    config = load_gmail_integration_config(settings)

    assert isinstance(config, GmailIntegrationConfig)
    assert config.allowed_from_addresses == ["alerts@example.com"]
    assert config.max_messages_per_poll == 11
    assert config.launchd_poll_interval_seconds == 240
    assert config.launchd_max_messages == 7


def test_load_gmail_integration_config_rejects_invalid_runtime_values(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_dir / "gmail_integration.json").write_text(
        json.dumps({"launchd_poll_interval_seconds": 0}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_gmail_integration_config(settings)


def test_load_gmail_integration_config_rejects_invalid_allowed_from_addresses(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_dir / "gmail_integration.json").write_text(
        json.dumps({"allowed_from_addresses": ["not-an-email"]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_gmail_integration_config(settings)


def test_load_gmail_integration_config_merges_local_override(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        templates_dir=Path("app/templates"),
        static_dir=Path("app/static"),
    )
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    settings.config_local_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_dir / "gmail_integration.json").write_text(
        json.dumps({"allowed_from_addresses": [], "max_messages_per_poll": 11}),
        encoding="utf-8",
    )
    (settings.config_local_dir / "gmail_integration.json").write_text(
        json.dumps({"allowed_from_addresses": ["Owner <owner@example.com>"]}),
        encoding="utf-8",
    )

    config = load_gmail_integration_config(settings)

    assert config.allowed_from_addresses == ["owner@example.com"]
    assert config.max_messages_per_poll == 11
