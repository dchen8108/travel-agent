from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from app.jobs.cli_types import positive_int_argument
from app.services.launchd import (
    CALENDAR_SYNC_LAUNCH_AGENT_LABEL,
    build_calendar_sync_launch_agent_plist,
    default_log_paths,
    installation_summary,
    launch_agent_domain,
    launch_agent_plist_path,
    launch_agent_target,
)
from app.settings import get_settings
from app.storage.repository import Repository


def _bootout_if_loaded(plist_path: Path) -> None:
    subprocess.run(
        ["launchctl", "bootout", launch_agent_domain(), str(plist_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> None:
    settings = get_settings()
    app_state = Repository(settings).load_app_state()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--interval-seconds",
        type=positive_int_argument("--interval-seconds"),
        default=app_state.launchd_calendar_sync_interval_seconds,
    )
    args = parser.parse_args()

    project_root = settings.project_root
    uv_executable = shutil.which("uv")
    if not uv_executable:
        raise SystemExit("Could not find `uv` in PATH.")

    stdout_log_path, stderr_log_path = default_log_paths(project_root, "sync_booking_calendar")
    stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agent_plist_path(CALENDAR_SYNC_LAUNCH_AGENT_LABEL)
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    plist_payload = build_calendar_sync_launch_agent_plist(
        uv_executable=uv_executable,
        project_root=project_root,
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
        start_interval_seconds=args.interval_seconds,
    )

    _bootout_if_loaded(plist_path)
    plist_path.write_bytes(plist_payload)
    subprocess.run(
        ["launchctl", "bootstrap", launch_agent_domain(), str(plist_path)],
        check=True,
    )
    subprocess.run(
        ["launchctl", "kickstart", "-k", launch_agent_target(CALENDAR_SYNC_LAUNCH_AGENT_LABEL)],
        check=True,
    )
    print(
        installation_summary(
            label=CALENDAR_SYNC_LAUNCH_AGENT_LABEL,
            plist_path=plist_path,
            interval_seconds=args.interval_seconds,
            extra_summary="reconciles active bookings into the Flights calendar",
        )
    )
    print(f"Logs: {stdout_log_path} and {stderr_log_path}")


if __name__ == "__main__":
    main()
