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
from app.settings import get_settings


def _bootout_if_loaded(plist_path: Path) -> None:
    subprocess.run(
        ["launchctl", "bootout", launch_agent_domain(), str(plist_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-seconds", type=int, default=180)
    parser.add_argument("--max-messages", type=int, default=10)
    args = parser.parse_args()

    settings = get_settings()
    project_root = settings.project_root
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

