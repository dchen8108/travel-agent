from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest

from app.jobs import install_launchd_booking_poller, install_launchd_fetcher
from app.models.base import AppState
from app.models.gmail_integration import GmailIntegrationConfig
from app.services.launchd import (
    BOOKING_POLLER_LAUNCH_AGENT_LABEL,
    LAUNCH_AGENT_LABEL,
    build_booking_poller_launch_agent_plist,
    build_launch_agent_plist,
    launch_agent_target,
)
from app.services.runtime_secrets import ensure_local_secret_from_env
from app.settings import Settings


def test_launch_agent_plist_contains_expected_program_arguments() -> None:
    payload = build_launch_agent_plist(
        uv_executable="/usr/local/bin/uv",
        project_root=Path("/Users/example/code/travel-agent"),
        stdout_log_path=Path("/Users/example/code/travel-agent/data/logs/fetch.stdout.log"),
        stderr_log_path=Path("/Users/example/code/travel-agent/data/logs/fetch.stderr.log"),
        start_interval_seconds=60,
        max_targets=2,
    )

    plist = plistlib.loads(payload)

    assert plist["Label"] == LAUNCH_AGENT_LABEL
    assert plist["ProgramArguments"] == [
        "/usr/local/bin/uv",
        "run",
        "python",
        "-m",
        "app.jobs.fetch_google_flights",
        "--max-targets",
        "2",
    ]
    assert plist["WorkingDirectory"] == "/Users/example/code/travel-agent"
    assert plist["RunAtLoad"] is True
    assert plist["StartInterval"] == 60


def test_booking_poller_launch_agent_plist_contains_expected_program_arguments() -> None:
    payload = build_booking_poller_launch_agent_plist(
        uv_executable="/usr/local/bin/uv",
        project_root=Path("/Users/example/code/travel-agent"),
        stdout_log_path=Path("/Users/example/code/travel-agent/data/logs/poll.stdout.log"),
        stderr_log_path=Path("/Users/example/code/travel-agent/data/logs/poll.stderr.log"),
        start_interval_seconds=180,
        max_messages=10,
    )

    plist = plistlib.loads(payload)

    assert plist["Label"] == BOOKING_POLLER_LAUNCH_AGENT_LABEL
    assert plist["ProgramArguments"] == [
        "/usr/local/bin/uv",
        "run",
        "python",
        "-m",
        "app.jobs.poll_gmail_bookings",
        "--max-messages",
        "10",
    ]
    assert plist["WorkingDirectory"] == "/Users/example/code/travel-agent"
    assert plist["RunAtLoad"] is True
    assert plist["StartInterval"] == 180


def test_ensure_local_secret_from_env_persists_launchd_compatible_key(tmp_path, monkeypatch) -> None:
    settings = Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "config")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    path = ensure_local_secret_from_env(
        settings,
        env_var="OPENAI_API_KEY",
        local_filename="openai_api_key.txt",
    )

    assert path == settings.config_local_dir / "openai_api_key.txt"
    assert path.read_text(encoding="utf-8").strip() == "sk-test-secret"


def test_ensure_local_secret_from_env_updates_rotated_key(tmp_path, monkeypatch) -> None:
    settings = Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "config")
    secret_path = settings.config_local_dir / "openai_api_key.txt"
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text("sk-old-secret\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-new-secret")

    path = ensure_local_secret_from_env(
        settings,
        env_var="OPENAI_API_KEY",
        local_filename="openai_api_key.txt",
    )

    assert path == secret_path
    assert secret_path.read_text(encoding="utf-8").strip() == "sk-new-secret"


def test_install_launchd_fetcher_rejects_invalid_interval(settings, monkeypatch) -> None:
    monkeypatch.setattr(install_launchd_fetcher, "get_settings", lambda: settings)

    class StubRepository:
        def __init__(self, _settings):
            pass

        def load_app_state(self):
            return AppState()

    monkeypatch.setattr(install_launchd_fetcher, "Repository", StubRepository)
    monkeypatch.setattr(sys, "argv", ["install_launchd_fetcher", "--interval-seconds", "0"])

    with pytest.raises(SystemExit):
        install_launchd_fetcher.main()


def test_install_launchd_booking_poller_rejects_invalid_message_limit(settings, monkeypatch) -> None:
    monkeypatch.setattr(install_launchd_booking_poller, "get_settings", lambda: settings)
    monkeypatch.setattr(
        install_launchd_booking_poller,
        "load_gmail_integration_config",
        lambda _settings: GmailIntegrationConfig(),
    )
    monkeypatch.setattr(sys, "argv", ["install_launchd_booking_poller", "--max-messages", "0"])

    with pytest.raises(SystemExit):
        install_launchd_booking_poller.main()


def test_install_launchd_fetcher_fails_cleanly_when_uv_missing(settings, monkeypatch) -> None:
    monkeypatch.setattr(install_launchd_fetcher, "get_settings", lambda: settings)

    class StubRepository:
        def __init__(self, _settings):
            pass

        def load_app_state(self):
            return AppState()

    monkeypatch.setattr(install_launchd_fetcher, "Repository", StubRepository)
    monkeypatch.setattr(install_launchd_fetcher.shutil, "which", lambda _name: None)
    monkeypatch.setattr(sys, "argv", ["install_launchd_fetcher"])

    with pytest.raises(SystemExit, match="Could not find `uv` in PATH."):
        install_launchd_fetcher.main()


def test_install_launchd_booking_poller_fails_cleanly_when_uv_missing(settings, monkeypatch) -> None:
    monkeypatch.setattr(install_launchd_booking_poller, "get_settings", lambda: settings)
    monkeypatch.setattr(
        install_launchd_booking_poller,
        "load_gmail_integration_config",
        lambda _settings: GmailIntegrationConfig(),
    )
    monkeypatch.setattr(
        install_launchd_booking_poller,
        "openai_api_key",
        lambda _settings: "sk-test-secret",
    )
    monkeypatch.setattr(
        install_launchd_booking_poller,
        "ensure_local_secret_from_env",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(install_launchd_booking_poller.shutil, "which", lambda _name: None)
    monkeypatch.setattr(sys, "argv", ["install_launchd_booking_poller"])

    with pytest.raises(SystemExit, match="Could not find `uv` in PATH."):
        install_launchd_booking_poller.main()


def test_install_launchd_booking_poller_writes_plist_and_persists_secret(tmp_path, monkeypatch, capsys) -> None:
    settings = Settings(data_dir=tmp_path / "data", config_dir=tmp_path / "config")
    plist_path = tmp_path / "LaunchAgents" / "com.test.poller.plist"
    stdout_log_path = tmp_path / "logs" / "poll.stdout.log"
    stderr_log_path = tmp_path / "logs" / "poll.stderr.log"
    run_calls: list[list[str]] = []

    monkeypatch.setattr(install_launchd_booking_poller, "get_settings", lambda: settings)
    monkeypatch.setattr(
        install_launchd_booking_poller,
        "load_gmail_integration_config",
        lambda _settings: GmailIntegrationConfig(),
    )
    monkeypatch.setattr(install_launchd_booking_poller.shutil, "which", lambda _name: "/usr/local/bin/uv")
    monkeypatch.setattr(
        install_launchd_booking_poller,
        "launch_agent_plist_path",
        lambda _label: plist_path,
    )
    monkeypatch.setattr(
        install_launchd_booking_poller,
        "default_log_paths",
        lambda _project_root, _job_name: (stdout_log_path, stderr_log_path),
    )
    monkeypatch.setattr(
        install_launchd_booking_poller.subprocess,
        "run",
        lambda args, **_kwargs: run_calls.append(list(args)),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-launchd-secret")
    monkeypatch.setattr(sys, "argv", ["install_launchd_booking_poller", "--interval-seconds", "240", "--max-messages", "12"])

    install_launchd_booking_poller.main()

    assert plist_path.exists()
    plist = plistlib.loads(plist_path.read_bytes())
    assert plist["ProgramArguments"] == [
        "/usr/local/bin/uv",
        "run",
        "python",
        "-m",
        "app.jobs.poll_gmail_bookings",
        "--max-messages",
        "12",
    ]
    assert settings.config_local_dir.joinpath("openai_api_key.txt").read_text(encoding="utf-8").strip() == "sk-launchd-secret"
    assert run_calls == [
        ["launchctl", "bootout", "gui/501", str(plist_path)],
        ["launchctl", "bootstrap", "gui/501", str(plist_path)],
        ["launchctl", "kickstart", "-k", launch_agent_target(BOOKING_POLLER_LAUNCH_AGENT_LABEL)],
    ]
    captured = capsys.readouterr()
    assert BOOKING_POLLER_LAUNCH_AGENT_LABEL in captured.out
