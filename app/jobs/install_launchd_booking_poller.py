from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from app.services.launchd import (
    BOOKING_POLLER_LAUNCH_AGENT_LABEL,
    build_booking_poller_launch_agent_plist,
    default_log_paths,
    installation_summary,
    launch_agent_domain,
    launch_agent_plist_path,
    launch_agent_target,
)
from app.services.gmail_config import load_gmail_integration_config
from app.services.runtime_secrets import ensure_local_secret_from_env, openai_api_key
from app.settings import get_settings


def _bootout_if_loaded(plist_path: Path) -> None:
    subprocess.run(
        ["launchctl", "bootout", launch_agent_domain(), str(plist_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> None:
    settings = get_settings()
    config = load_gmail_integration_config(settings)
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-seconds", type=int, default=config.launchd_poll_interval_seconds)
    parser.add_argument("--max-messages", type=int, default=config.launchd_max_messages)
    args = parser.parse_args()

    project_root = settings.project_root
    ensure_local_secret_from_env(
        settings,
        env_var="OPENAI_API_KEY",
        local_filename="openai_api_key.txt",
    )
    if not openai_api_key(settings):
        raise SystemExit(
            "OPENAI_API_KEY is not configured for launchd. Set it in your shell and rerun this installer, "
            "or write config/local/openai_api_key.txt."
        )
    uv_executable = shutil.which("uv")
    if not uv_executable:
        raise SystemExit("Could not find `uv` in PATH.")

    stdout_log_path, stderr_log_path = default_log_paths(project_root, "poll_gmail_bookings")
    stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agent_plist_path(BOOKING_POLLER_LAUNCH_AGENT_LABEL)
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    plist_payload = build_booking_poller_launch_agent_plist(
        uv_executable=uv_executable,
        project_root=project_root,
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
        start_interval_seconds=args.interval_seconds,
        max_messages=args.max_messages,
    )

    _bootout_if_loaded(plist_path)
    plist_path.write_bytes(plist_payload)
    subprocess.run(
        ["launchctl", "bootstrap", launch_agent_domain(), str(plist_path)],
        check=True,
    )
    subprocess.run(
        ["launchctl", "kickstart", "-k", launch_agent_target(BOOKING_POLLER_LAUNCH_AGENT_LABEL)],
        check=True,
    )
    print(
        installation_summary(
            label=BOOKING_POLLER_LAUNCH_AGENT_LABEL,
            plist_path=plist_path,
            interval_seconds=args.interval_seconds,
            extra_summary=f"max_messages={args.max_messages}",
        )
    )
    print(f"Logs: {stdout_log_path} and {stderr_log_path}")


if __name__ == "__main__":
    main()
