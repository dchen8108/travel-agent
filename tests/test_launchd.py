from __future__ import annotations
import plistlib
from pathlib import Path

from app.services.launchd import (
    BOOKING_POLLER_LAUNCH_AGENT_LABEL,
    LAUNCH_AGENT_LABEL,
    build_booking_poller_launch_agent_plist,
    build_launch_agent_plist,
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
